using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NetMQ;
using NetMQ.Sockets;
using TradingPlatform.BusinessLayer;

namespace OverseerBridge;

public sealed class OverseerBridge : Strategy
{
    private const string BridgeVersion = "2026-06-01.2";

    [InputParameter("Target symbols CSV", 0)]
    public string TargetSymbols { get; set; } = "6EM6,6BM6,6JM6,6AM6,6CM6,6NM6,6SM6,6MM6,EUR/USD,GBP/USD,USD/JPY,AUD/USD,USD/CAD,NZD/USD,USD/CHF,EUR/GBP,EUR/JPY,GBP/JPY,AUD/JPY,CAD/JPY,CHF/JPY,NZD/JPY,EUR/AUD,EUR/CAD,EUR/CHF,EUR/NZD,GBP/AUD,GBP/CAD,GBP/CHF,GBP/NZD,AUD/CAD,AUD/CHF,AUD/NZD,CAD/CHF,NZD/CAD,NZD/CHF,XAU/USD,XAG/USD";

    [InputParameter("UDP host", 1)]
    public string UdpHost { get; set; } = "127.0.0.1";

    [InputParameter("UDP port", 2)]
    public int UdpPort { get; set; } = 65000;

    [InputParameter("DOM depth", 3)]
    public int DomDepth { get; set; } = 10;

    [InputParameter("ZMQ port", 4)]
    public int ZmqPort { get; set; } = 5555;

    [InputParameter("Enable ZMQ", 5)]
    public bool ZmqEnabled { get; set; } = true;

    [InputParameter("ZMQ heartbeat interval (s)", 6)]
    public int ZmqHeartbeatInterval { get; set; } = 5;

    [InputParameter("Log directory", 7)]
    public string LogDirectory { get; set; } = @"C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer\logs";

    private readonly object sync = new();
    private readonly object logSync = new();
    private string logPath = @"C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer\logs\bridge.log";
    private string rawLevel2Path = @"C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer\logs\quantower_l3_raw.jsonl";
    private readonly Dictionary<string, SymbolState> symbolStates = new(StringComparer.OrdinalIgnoreCase);
    private UdpClient? udp;
    private IPEndPoint? endpoint;
    private PublisherSocket? zmqPub;
    private CancellationTokenSource? reconnectCts;
    private bool reconnectLoopActive;
    private long zmqMessagesSent;
    private long zmqMboEventsSent;
    private DateTime lastHeartbeat = DateTime.MinValue;

    public OverseerBridge()
    {
        Name = $"OVERSEER v12 UDP Bridge {BridgeVersion}";
        Description = "Broadcasts Quantower/Rithmic L2/L3 DOM ticks to OVERSEER backend.";
    }

    protected override void OnRun()
    {
        try
        {
            logPath = Path.Combine(LogDirectory, "bridge.log");
            rawLevel2Path = Path.Combine(LogDirectory, "quantower_l3_raw.jsonl");
            Directory.CreateDirectory(LogDirectory);
            LogFile($"Starting OVERSEER bridge version={BridgeVersion}.");
            udp = new UdpClient();
            endpoint = new IPEndPoint(IPAddress.Parse(UdpHost), UdpPort);
            SendStartupHeartbeat();
            
            if (ZmqEnabled)
            {
                zmqPub = new PublisherSocket();
                zmqPub.Options.SendHighWatermark = 1000;
                zmqPub.Bind($"tcp://*:{ZmqPort}");
                LogFile($"ZMQ Publisher bound to tcp://*:{ZmqPort}");
            }

            reconnectCts = new CancellationTokenSource();
            ConnectAndSubscribe();
        }
        catch (Exception ex)
        {
            LogFile("Startup failure: " + ex);
            StartReconnectLoop();
        }
    }

    protected override void OnStop()
    {
        try
        {
            reconnectCts?.Cancel();
            Unsubscribe();
            udp?.Dispose();
            udp = null;
            
            if (zmqPub != null)
            {
                zmqPub.Dispose();
                zmqPub = null;
                LogFile("ZMQ Publisher disposed.");
            }

            LogFile("Bridge stopped.");
        }
        catch (Exception ex)
        {
            LogFile("Stop failure: " + ex);
        }
    }

    private void ConnectAndSubscribe()
    {
        Unsubscribe();
        var requested = TargetSymbols
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        if (requested.Length == 0)
            throw new InvalidOperationException("At least one target symbol is required.");

        foreach (string requestedSymbol in requested)
        {
            Symbol? symbol = Core.Instance.Symbols.FirstOrDefault(s =>
                string.Equals(s.Name, requestedSymbol, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(s.Id, requestedSymbol, StringComparison.OrdinalIgnoreCase));

            if (symbol == null)
            {
                LogFile($"Symbol '{requestedSymbol}' was not found in active Quantower connections.");
                continue;
            }

            symbol.NewLevel2 += OnNewLevel2;
            symbolStates[symbol.Name] = new SymbolState(symbol);
            LogFile($"Subscribed to Level 2/Level 3 DOM for {symbol.Name} via Quantower connection.");
        }

        if (symbolStates.Count == 0)
            throw new InvalidOperationException($"None of the requested symbols were found: {TargetSymbols}");
    }

    private void Unsubscribe()
    {
        foreach (var state in symbolStates.Values.ToArray())
        {
            try
            {
                state.Symbol.NewLevel2 -= OnNewLevel2;
            }
            catch (Exception ex)
            {
                LogFile($"Unsubscribe failure for {state.Symbol.Name}: {ex}");
            }
        }

        symbolStates.Clear();
    }

    private void OnNewLevel2(Symbol sender, Level2Quote level2, DOMQuote dom)
    {
        try
        {
            if (sender == null || level2 == null)
                return;

            lock (sync)
            {
                string symbolName = !string.IsNullOrWhiteSpace(sender.Name) ? sender.Name : sender.Id;
                if (string.IsNullOrWhiteSpace(symbolName))
                    return;

                if (!symbolStates.TryGetValue(symbolName, out SymbolState? state))
                    state = symbolStates[symbolName] = new SymbolState(sender);

                WriteRawLevel2(symbolName, level2, dom);

                string level2Side = level2.PriceType.ToString();
                double level2Price = double.IsFinite(level2.Price) ? level2.Price : 0;
                double level2Size = double.IsFinite(level2.Size) ? level2.Size : 0;
                if (level2Price > 0)
                {
                    if (level2Side.Contains("Ask", StringComparison.OrdinalIgnoreCase) ||
                        level2Side.Contains("Offer", StringComparison.OrdinalIgnoreCase))
                    {
                        state.LastAsk = level2Price;
                        if (level2Size > 0)
                            state.LastAskSize = level2Size;
                    }
                    else
                    {
                        state.LastBid = level2Price;
                        if (level2Size > 0)
                            state.LastBidSize = level2Size;
                    }
                }

                double bestBid = FirstFinitePositive(
                    dom?.Bids?.Where(q => q != null).Select(q => q.Price),
                    double.IsFinite(sender.Bid) ? sender.Bid : 0,
                    state.LastBid);
                double bestAsk = FirstFinitePositive(
                    dom?.Asks?.Where(q => q != null).Select(q => q.Price),
                    double.IsFinite(sender.Ask) ? sender.Ask : 0,
                    state.LastAsk);
                if (bestBid <= 0 &&
                    level2Price > 0 &&
                    !level2Side.Contains("Ask", StringComparison.OrdinalIgnoreCase) &&
                    !level2Side.Contains("Offer", StringComparison.OrdinalIgnoreCase))
                {
                    bestBid = level2Price;
                }
                if (bestAsk <= 0 &&
                    level2Price > 0 &&
                    (level2Side.Contains("Ask", StringComparison.OrdinalIgnoreCase) ||
                     level2Side.Contains("Offer", StringComparison.OrdinalIgnoreCase)))
                {
                    bestAsk = level2Price;
                }
                if (bestBid <= 0 || bestAsk <= 0 || bestAsk <= bestBid)
                    return;

                double bestBidSize = FirstFinitePositive(
                    dom?.Bids?.Where(q => q != null).Select(q => q.Size),
                    double.IsFinite(sender.BidSize) ? sender.BidSize : 0,
                    state.LastBidSize);
                double bestAskSize = FirstFinitePositive(
                    dom?.Asks?.Where(q => q != null).Select(q => q.Size),
                    double.IsFinite(sender.AskSize) ? sender.AskSize : 0,
                    state.LastAskSize);

                state.CumulativeDelta += (bestAskSize - state.LastAskSize) - (bestBidSize - state.LastBidSize);
                state.LastBid = bestBid;
                state.LastAsk = bestAsk;
                state.LastBidSize = bestBidSize;
                state.LastAskSize = bestAskSize;

                var snapshot = BuildDomSnapshot(dom, level2);
                string domJson = JsonSerializer.Serialize(snapshot);
                long timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

                string payload = string.Join("|", new[]
                {
                    symbolName,
                    bestBid.ToString("G17", CultureInfo.InvariantCulture),
                    bestBidSize.ToString("G17", CultureInfo.InvariantCulture),
                    bestAsk.ToString("G17", CultureInfo.InvariantCulture),
                    bestAskSize.ToString("G17", CultureInfo.InvariantCulture),
                    domJson,
                    state.CumulativeDelta.ToString("G17", CultureInfo.InvariantCulture),
                    timestamp.ToString(CultureInfo.InvariantCulture)
                });

                byte[] bytes = Encoding.UTF8.GetBytes(payload);
                udp?.Send(bytes, bytes.Length, endpoint);

                if (ZmqEnabled && zmqPub != null)
                {
                    var zmqPayloadObj = new
                    {
                        symbol = symbolName,
                        bid = bestBid,
                        ask = bestAsk,
                        bid_size = bestBidSize,
                        ask_size = bestAskSize,
                        dom = snapshot,
                        delta = state.CumulativeDelta,
                        timestamp = timestamp
                    };
                    string zmqJson = JsonSerializer.Serialize(zmqPayloadObj);
                    zmqPub.SendMoreFrame("OVERSEER_L3").SendFrame(zmqJson);
                    Interlocked.Increment(ref zmqMessagesSent);

                    if (level2 != null && !string.IsNullOrEmpty(level2.Id))
                    {
                        var mboEvent = new
                        {
                            type = "mbo_event",
                            symbol = symbolName,
                            action = level2.Size > 0 ? "MODIFY" : "CANCEL",
                            order_id = level2.Id,
                            price = level2Price,
                            size = level2Size,
                            side = level2Side,
                            timestamp_ns = timestamp * 1_000_000
                        };
                        string mboJson = JsonSerializer.Serialize(mboEvent);
                        zmqPub.SendMoreFrame("OVERSEER_L3").SendFrame(mboJson);
                        Interlocked.Increment(ref zmqMboEventsSent);
                    }

                    if (ZmqHeartbeatInterval > 0 && (DateTime.UtcNow - lastHeartbeat).TotalSeconds >= ZmqHeartbeatInterval)
                    {
                        lastHeartbeat = DateTime.UtcNow;
                        var heartbeat = new
                        {
                            type = "heartbeat",
                            version = BridgeVersion,
                            symbols_tracked = symbolStates.Count,
                            zmq_messages_sent = Interlocked.Read(ref zmqMessagesSent),
                            zmq_mbo_events_sent = Interlocked.Read(ref zmqMboEventsSent),
                            timestamp = timestamp
                        };
                        string hbJson = JsonSerializer.Serialize(heartbeat);
                        zmqPub.SendMoreFrame("OVERSEER_L3").SendFrame(hbJson);
                    }
                }
            }
        }
        catch (Exception ex)
        {
            LogFile("Tick handling failure: " + ex);
        }
    }

    private Dictionary<string, object> BuildDomSnapshot(DOMQuote? dom, Level2Quote level2)
    {
        var bids = new List<DomLevel>();
        var asks = new List<DomLevel>();

        if (dom?.Bids != null)
        {
            foreach (var quote in dom.Bids.Where(q => q != null).Take(Math.Max(1, DomDepth)))
                bids.Add(DomLevel.FromQuote(quote));
        }

        if (dom?.Asks != null)
        {
            foreach (var quote in dom.Asks.Where(q => q != null).Take(Math.Max(1, DomDepth)))
                asks.Add(DomLevel.FromQuote(quote));
        }

        if (bids.Count == 0 && asks.Count == 0 && level2.Price > 0)
        {
            string priceType = level2.PriceType.ToString();
            if (priceType.Contains("Ask", StringComparison.OrdinalIgnoreCase) ||
                priceType.Contains("Offer", StringComparison.OrdinalIgnoreCase))
            {
                asks.Add(DomLevel.FromQuote(level2));
            }
            else
            {
                bids.Add(DomLevel.FromQuote(level2));
            }
        }

        return new Dictionary<string, object>
        {
            ["bids"] = bids,
            ["asks"] = asks,
            ["source"] = "quantower"
        };
    }

    private void WriteRawLevel2(string symbolName, Level2Quote level2, DOMQuote? dom)
    {
        try
        {
            var raw = new
            {
                source = "quantower",
                version = BridgeVersion,
                symbol = symbolName,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                quote = DomLevel.FromQuote(level2),
                quotePriceType = level2.PriceType.ToString(),
                domBidCount = dom?.Bids?.Count ?? 0,
                domAskCount = dom?.Asks?.Count ?? 0,
                domTopBid = dom?.Bids?.Where(q => q != null).Select(DomLevel.FromQuote).FirstOrDefault(),
                domTopAsk = dom?.Asks?.Where(q => q != null).Select(DomLevel.FromQuote).FirstOrDefault()
            };

            string line = JsonSerializer.Serialize(raw) + Environment.NewLine;
            lock (logSync)
            {
                using var stream = new FileStream(rawLevel2Path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite);
                using var writer = new StreamWriter(stream);
                writer.Write(line);
            }
        }
        catch (Exception ex)
        {
            LogFile("Raw L3 log failure: " + ex.Message);
        }
    }

    private static double FirstFinitePositive(IEnumerable<double>? values, params double[] fallbacks)
    {
        if (values != null)
        {
            foreach (double value in values)
            {
                if (double.IsFinite(value) && value > 0)
                    return value;
            }
        }

        foreach (double value in fallbacks)
        {
            if (double.IsFinite(value) && value > 0)
                return value;
        }

        return 0;
    }

    private void StartReconnectLoop()
    {
        if (reconnectCts == null || reconnectCts.IsCancellationRequested)
            reconnectCts = new CancellationTokenSource();

        lock (sync)
        {
            if (reconnectLoopActive)
                return;
            reconnectLoopActive = true;
        }

        var token = reconnectCts.Token;
        Task.Run(async () =>
        {
            while (!token.IsCancellationRequested)
            {
                try
                {
                    await Task.Delay(TimeSpan.FromSeconds(5), token);
                    LogFile("Attempting bridge reconnect.");
                    ConnectAndSubscribe();
                    LogFile("Bridge reconnect successful.");
                    lock (sync)
                        reconnectLoopActive = false;
                    return;
                }
                catch (OperationCanceledException)
                {
                    lock (sync)
                        reconnectLoopActive = false;
                    return;
                }
                catch (Exception ex)
                {
                    LogFile("Reconnect failed: " + ex.Message);
                }
            }
        }, token);
    }

    private void SendStartupHeartbeat()
    {
        if (udp == null || endpoint == null)
            return;

        var payload = JsonSerializer.Serialize(new
        {
            type = "overseer_bridge_startup",
            version = BridgeVersion,
            target_symbols = TargetSymbols,
            udp_host = UdpHost,
            udp_port = UdpPort,
            zmq_enabled = ZmqEnabled,
            zmq_port = ZmqPort,
            timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
        });

        byte[] bytes = Encoding.UTF8.GetBytes(payload);
        udp.Send(bytes, bytes.Length, endpoint);
        LogFile("Startup UDP heartbeat sent.");
    }

    private void LogFile(string message)
    {
        string line = $"{DateTimeOffset.UtcNow:O} {message}{Environment.NewLine}";
        lock (logSync)
        {
            using var stream = new FileStream(logPath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite);
            using var writer = new StreamWriter(stream);
            writer.Write(line);
        }
        Log(message, StrategyLoggingLevel.Info);
    }

    private sealed record DomLevel(
        double Price,
        double Size,
        string? Id,
        long Priority,
        int NumberOrders,
        string? Broker,
        double ImpliedSize)
    {
        public static DomLevel FromQuote(Level2Quote quote)
        {
            return new DomLevel(
                quote.Price,
                quote.Size,
                quote.Id,
                quote.Priority,
                quote.NumberOrders,
                quote.Broker,
                quote.ImpliedSize);
        }
    }

    private sealed class SymbolState
    {
        public SymbolState(Symbol symbol)
        {
            Symbol = symbol;
        }

        public Symbol Symbol { get; }
        public double CumulativeDelta { get; set; }
        public double LastBid { get; set; }
        public double LastAsk { get; set; }
        public double LastBidSize { get; set; }
        public double LastAskSize { get; set; }
    }
}
