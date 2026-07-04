from __future__ import annotations

"""OVERSEER – Multi-Timeframe OHLCV Candle Aggregator.

Consumes raw tick dicts produced by the UDP bridge and aggregates them
into OHLCV candles across six standard forex timeframes.  Every completed
candle receives rolling EMA(20), EMA(50) and RSI(14) calculations that
are maintained incrementally so the cost per tick stays O(1).

Thread-safe: every public method acquires an internal ``threading.Lock``
before touching shared state.

Typical integration::

    agg = CandleAggregator()
    # inside your tick-processing loop
    agg.process_tick(tick)

    # periodically
    with sqlite3.connect(str(DB_PATH)) as conn:
        agg.flush_to_db(conn)
"""

import logging
import math
import sqlite3
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional, Tuple

LOGGER = logging.getLogger("overseer.candle_aggregator")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMEFRAMES: Dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1H": 3600,
    "4H": 14400,
    "Daily": 86400,
}

_CANDLE_BUFFER_MAXLEN: int = 500

_JPY_PAIRS = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY"}
_XAU_SYMBOLS = {"XAUUSD", "GOLD"}

# DB DDL – executed lazily on first flush if the table does not yet exist.
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS candle_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT    NOT NULL,
    timeframe  TEXT    NOT NULL,
    open_time  TEXT    NOT NULL,
    close_time TEXT    NOT NULL,
    open       REAL    NOT NULL,
    high       REAL    NOT NULL,
    low        REAL    NOT NULL,
    close      REAL    NOT NULL,
    volume     REAL    NOT NULL,
    tick_count INTEGER NOT NULL,
    ema_20     REAL,
    ema_50     REAL,
    rsi_14     REAL
);
"""

_INSERT_SQL = """
INSERT OR IGNORE INTO candle_history
(symbol, timeframe, open_time, close_time, open, high, low, close,
 volume, tick_count, ema_20, ema_50, rsi_14)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pip_size(symbol: str) -> float:
    """Return the pip multiplier for *symbol*.

    JPY crosses and gold use 0.01; everything else uses 0.0001.
    """
    sym_upper = symbol.upper()
    if sym_upper in _XAU_SYMBOLS or "JPY" in sym_upper:
        return 0.01
    return 0.0001


def _align_open_time(ts_epoch: float, period_seconds: int) -> float:
    """Return the epoch second of the period boundary that *ts_epoch* belongs to."""
    return (ts_epoch // period_seconds) * period_seconds


# ---------------------------------------------------------------------------
# Candle dataclass
# ---------------------------------------------------------------------------

@dataclass
class Candle:
    """Represents a single OHLCV candle with optional indicator values."""

    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    tick_count: int
    open_time: datetime
    close_time: datetime
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    rsi_14: Optional[float] = None
    flushed: bool = False


# ---------------------------------------------------------------------------
# Internal indicator state
# ---------------------------------------------------------------------------

@dataclass
class _EmaState:
    """Tracks the running EMA value and whether it has been seeded."""
    period: int
    value: Optional[float] = None
    count: int = 0

    @property
    def multiplier(self) -> float:
        return 2.0 / (self.period + 1)

    def update(self, price: float) -> Optional[float]:
        """Feed a new close price and return the updated EMA."""
        self.count += 1
        if self.value is None:
            self.value = price
        else:
            k = self.multiplier
            self.value = price * k + self.value * (1.0 - k)
        return self.value


@dataclass
class _RsiState:
    """Wilder-smoothed RSI(14) running state."""
    period: int = 14
    avg_gain: Optional[float] = None
    avg_loss: Optional[float] = None
    prev_close: Optional[float] = None
    count: int = 0

    def update(self, price: float) -> Optional[float]:
        """Feed a new close price and return the updated RSI, or ``None``
        if fewer than *period* + 1 data points have been received."""
        self.count += 1
        if self.prev_close is None:
            self.prev_close = price
            return None

        change = price - self.prev_close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        self.prev_close = price

        if self.avg_gain is None:
            # Still in the seed window – accumulate.
            # We'll store partial sums in avg_gain / avg_loss until we have
            # enough data points.
            self.avg_gain = 0.0
            self.avg_loss = 0.0

        if self.count <= self.period + 1:
            # Accumulate for the initial SMA-based seed.
            self.avg_gain += gain
            self.avg_loss += loss
            if self.count == self.period + 1:
                self.avg_gain /= self.period
                self.avg_loss /= self.period
                return self._rsi()
            return None

        # Wilder smoothing after seed.
        self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
        self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period
        return self._rsi()

    def _rsi(self) -> float:
        if self.avg_loss == 0.0:
            return 100.0
        rs = self.avg_gain / self.avg_loss  # type: ignore[operator]
        return 100.0 - (100.0 / (1.0 + rs))


@dataclass
class _IndicatorBundle:
    """Groups the rolling indicator states for one (symbol, timeframe) pair."""
    ema_20: _EmaState = field(default_factory=lambda: _EmaState(period=20))
    ema_50: _EmaState = field(default_factory=lambda: _EmaState(period=50))
    rsi_14: _RsiState = field(default_factory=_RsiState)

    def update(self, close: float) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Feed a close price and return (ema20, ema50, rsi14)."""
        return (
            self.ema_20.update(close),
            self.ema_50.update(close),
            self.rsi_14.update(close),
        )


# ---------------------------------------------------------------------------
# Working (in-progress) candle
# ---------------------------------------------------------------------------

@dataclass
class _WorkingCandle:
    """Mutable candle that is still accepting ticks."""
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    tick_count: int
    open_epoch: float          # aligned open in epoch seconds
    period_seconds: int

    @property
    def close_epoch(self) -> float:
        return self.open_epoch + self.period_seconds

    def contains(self, ts_epoch: float) -> bool:
        """Return ``True`` if *ts_epoch* falls within this candle's period."""
        return self.open_epoch <= ts_epoch < self.close_epoch

    def update(self, mid: float, volume: float) -> None:
        self.high = max(self.high, mid)
        self.low = min(self.low, mid)
        self.close = mid
        self.volume += volume
        self.tick_count += 1

    def finalise(
        self,
        ema_20: Optional[float],
        ema_50: Optional[float],
        rsi_14: Optional[float],
    ) -> Candle:
        """Freeze the working candle into an immutable :class:`Candle`."""
        return Candle(
            symbol=self.symbol,
            timeframe=self.timeframe,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=round(self.volume, 6),
            tick_count=self.tick_count,
            open_time=datetime.fromtimestamp(self.open_epoch, tz=timezone.utc),
            close_time=datetime.fromtimestamp(self.close_epoch, tz=timezone.utc),
            ema_20=round(ema_20, 6) if ema_20 is not None else None,
            ema_50=round(ema_50, 6) if ema_50 is not None else None,
            rsi_14=round(rsi_14, 2) if rsi_14 is not None else None,
        )


# ===================================================================
# Public API
# ===================================================================

class CandleAggregator:
    """Aggregates raw ticks into multi-timeframe OHLCV candles.

    Parameters
    ----------
    buffer_maxlen:
        Maximum number of completed candles kept in the in-memory ring
        buffer per (symbol, timeframe) pair.  Defaults to 500.
    """

    def __init__(self, buffer_maxlen: int = _CANDLE_BUFFER_MAXLEN) -> None:
        self._lock = threading.Lock()
        self._buffer_maxlen = buffer_maxlen

        # keyed by (symbol, timeframe)
        self._working: Dict[Tuple[str, str], _WorkingCandle] = {}
        self._completed: Dict[Tuple[str, str], Deque[Candle]] = {}
        self._indicators: Dict[Tuple[str, str], _IndicatorBundle] = {}

        # HVN tracking: per (symbol, timeframe), stores list of (poc_price, candle_close_time)
        self._hvn_history: Dict[Tuple[str, str], Deque[Tuple[float, datetime]]] = {}
        # Consecutive node cache: per symbol, list of double/triple node prices
        self._consecutive_nodes: Dict[str, list[dict[str, Any]]] = {}

        self._table_ensured = False
        LOGGER.info("CandleAggregator initialised (buffer_maxlen=%d)", buffer_maxlen)

    # ------------------------------------------------------------------
    # Tick ingestion
    # ------------------------------------------------------------------

    def process_tick(self, tick: dict) -> None:
        """Ingest a single tick and update all timeframe candles.

        Parameters
        ----------
        tick:
            Dict with keys: ``symbol``, ``bid``, ``ask``, ``bid_size``,
            ``ask_size``, ``timestamp`` (ms epoch).

        Raises
        ------
        KeyError
            If a required field is missing from *tick*.
        ValueError
            If numeric fields cannot be processed.
        """
        try:
            symbol: str = tick["symbol"]
            bid: float = float(tick["bid"])
            ask: float = float(tick["ask"])
            bid_size: float = float(tick["bid_size"])
            ask_size: float = float(tick["ask_size"])
            ts_ms: int = int(tick["timestamp"])
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("Tick rejected – bad payload: %s", exc)
            return

        mid = (bid + ask) / 2.0
        vol = bid_size + ask_size
        ts_epoch = ts_ms / 1000.0

        with self._lock:
            for tf_name, tf_seconds in TIMEFRAMES.items():
                self._ingest(symbol, tf_name, tf_seconds, mid, vol, ts_epoch)

    def _ingest(
        self,
        symbol: str,
        tf_name: str,
        tf_seconds: int,
        mid: float,
        vol: float,
        ts_epoch: float,
    ) -> None:
        """Core ingestion – must be called while holding ``self._lock``."""
        key = (symbol, tf_name)
        wc = self._working.get(key)

        if wc is not None and wc.contains(ts_epoch):
            wc.update(mid, vol)
            return

        # Finalise the previous candle if it exists.
        if wc is not None:
            self._finalise_candle(key, wc)

        # Start a new working candle.
        aligned = _align_open_time(ts_epoch, tf_seconds)
        self._working[key] = _WorkingCandle(
            symbol=symbol,
            timeframe=tf_name,
            open=mid,
            high=mid,
            low=mid,
            close=mid,
            volume=vol,
            tick_count=1,
            open_epoch=aligned,
            period_seconds=tf_seconds,
        )

    def _finalise_candle(
        self,
        key: Tuple[str, str],
        wc: _WorkingCandle,
    ) -> None:
        """Close a working candle, compute indicators, and store it."""
        bundle = self._indicators.setdefault(key, _IndicatorBundle())
        ema20, ema50, rsi14 = bundle.update(wc.close)
        candle = wc.finalise(ema20, ema50, rsi14)

        buf = self._completed.setdefault(
            key,
            deque(maxlen=self._buffer_maxlen),
        )
        buf.append(candle)

        # Track HVN (POC approximation = midpoint of candle range weighted by volume)
        hvn_buf = self._hvn_history.setdefault(key, deque(maxlen=100))
        candle_range = wc.high - wc.low
        if candle_range > 0 and wc.volume > 0:
            poc_price = wc.low + candle_range * 0.5
            hvn_buf.append((poc_price, candle.close_time))
            self._update_consecutive_nodes(key[0], key[1])

        LOGGER.debug(
            "Candle closed: %s %s %s  O=%.5f H=%.5f L=%.5f C=%.5f V=%.2f ticks=%d",
            candle.symbol,
            candle.timeframe,
            candle.open_time.isoformat(),
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
            candle.tick_count,
        )

    # ------------------------------------------------------------------
    # Completed candle accessors (internal, lock must be held)
    # ------------------------------------------------------------------

    def _get_candles(self, symbol: str, timeframe: str) -> Deque[Candle]:
        """Return the completed-candle buffer for *(symbol, timeframe)*.

        Returns an empty deque if nothing has been aggregated yet.
        Caller **must** hold ``self._lock``.
        """
        return self._completed.get((symbol, timeframe), deque())

    # ------------------------------------------------------------------
    # Analysis Methods
    # ------------------------------------------------------------------

    def get_trend_alignment(self, symbol: str) -> Dict[str, Any]:
        """Evaluate multi-timeframe trend alignment for *symbol*.

        Returns
        -------
        dict
            Keyed by timeframe with sub-keys ``price_vs_ema20``,
            ``price_vs_ema50``, ``rsi``, ``trend``.  An ``alignment_score``
            (int, -4 … +4) summarises the net bias across 15m, 1H, 4H,
            Daily.
        """
        scored_tfs = ("15m", "1H", "4H", "Daily")
        result: Dict[str, Any] = {}
        score = 0

        with self._lock:
            for tf_name in TIMEFRAMES:
                candles = self._get_candles(symbol, tf_name)
                if not candles:
                    result[tf_name] = {
                        "price_vs_ema20": "n/a",
                        "price_vs_ema50": "n/a",
                        "rsi": None,
                        "trend": "neutral",
                    }
                    continue

                last = candles[-1]
                vs_ema20 = self._compare_vs(last.close, last.ema_20)
                vs_ema50 = self._compare_vs(last.close, last.ema_50)
                rsi = last.rsi_14

                # Determine trend.
                if vs_ema20 == "above" and vs_ema50 == "above":
                    trend = "bullish"
                elif vs_ema20 == "below" and vs_ema50 == "below":
                    trend = "bearish"
                else:
                    trend = "neutral"

                result[tf_name] = {
                    "price_vs_ema20": vs_ema20,
                    "price_vs_ema50": vs_ema50,
                    "rsi": rsi,
                    "trend": trend,
                }

                if tf_name in scored_tfs:
                    if trend == "bullish":
                        score += 1
                    elif trend == "bearish":
                        score -= 1

        result["alignment_score"] = max(-4, min(4, score))
        return result

    @staticmethod
    def _compare_vs(price: float, ema: Optional[float]) -> str:
        if ema is None:
            return "n/a"
        return "above" if price >= ema else "below"

    # ------------------------------------------------------------------

    def get_session_range(self, symbol: str) -> Dict[str, Optional[float]]:
        """Return the Asian-session (00:00-08:00 UTC) high/low for today.

        Uses completed 15-minute candles whose open_time falls within the
        current UTC date's Asian session window.

        Returns
        -------
        dict
            ``asian_high``, ``asian_low``, ``range_pips``.  Values are
            ``None`` when no qualifying candles exist.
        """
        now_utc = datetime.now(tz=timezone.utc)
        session_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        session_end = now_utc.replace(hour=8, minute=0, second=0, microsecond=0)

        with self._lock:
            candles = self._get_candles(symbol, "15m")
            highs: list[float] = []
            lows: list[float] = []
            for c in candles:
                if session_start <= c.open_time < session_end:
                    highs.append(c.high)
                    lows.append(c.low)

        if not highs:
            return {"asian_high": None, "asian_low": None, "range_pips": None}

        asian_high = max(highs)
        asian_low = min(lows)
        pip = _pip_size(symbol)
        range_pips = round((asian_high - asian_low) / pip, 1)
        return {
            "asian_high": asian_high,
            "asian_low": asian_low,
            "range_pips": range_pips,
        }

    # ------------------------------------------------------------------

    def get_weekly_levels(self, symbol: str) -> Dict[str, Optional[float]]:
        """Derive weekly high, low, and open from the last 5 Daily candles.

        Returns
        -------
        dict
            ``weekly_high``, ``weekly_low``, ``weekly_open``.
        """
        with self._lock:
            candles = self._get_candles(symbol, "Daily")
            recent = list(candles)[-5:] if candles else []

        if not recent:
            return {"weekly_high": None, "weekly_low": None, "weekly_open": None}

        return {
            "weekly_high": max(c.high for c in recent),
            "weekly_low": min(c.low for c in recent),
            "weekly_open": recent[0].open,
        }

    # ------------------------------------------------------------------

    def detect_liquidity_sweep(self, symbol: str) -> Dict[str, Any]:
        """Check the last few 15m candles for a liquidity sweep.

        A **sweep** occurs when a wick extends beyond a recent swing
        level (highest high / lowest low of the preceding 10 candles)
        and then the close rejects back inside the range (wick is > 60 %
        of the total candle range).

        Returns
        -------
        dict
            ``sweep_detected``, ``sweep_type`` (``'high'`` / ``'low'``
            / ``None``), ``sweep_level``, ``rejection_strength``.
        """
        default: Dict[str, Any] = {
            "sweep_detected": False,
            "sweep_type": None,
            "sweep_level": None,
            "rejection_strength": 0.0,
        }

        with self._lock:
            candles = list(self._get_candles(symbol, "15m"))

        # Need at least 11 candles (10 for the swing window + 1 to test).
        if len(candles) < 11:
            return default

        # Use the last 3 candles as potential sweep candles.
        lookback = min(3, len(candles) - 10)
        swing_window = candles[-(10 + lookback):-lookback]
        test_candles = candles[-lookback:]

        swing_high = max(c.high for c in swing_window)
        swing_low = min(c.low for c in swing_window)

        for tc in reversed(test_candles):
            candle_range = tc.high - tc.low
            if candle_range == 0:
                continue

            # --- High sweep ---
            if tc.high > swing_high:
                upper_wick = tc.high - max(tc.open, tc.close)
                wick_ratio = upper_wick / candle_range
                if tc.close <= swing_high and wick_ratio > 0.6:
                    return {
                        "sweep_detected": True,
                        "sweep_type": "high",
                        "sweep_level": swing_high,
                        "rejection_strength": round(wick_ratio, 4),
                    }

            # --- Low sweep ---
            if tc.low < swing_low:
                lower_wick = min(tc.open, tc.close) - tc.low
                wick_ratio = lower_wick / candle_range
                if tc.close >= swing_low and wick_ratio > 0.6:
                    return {
                        "sweep_detected": True,
                        "sweep_type": "low",
                        "sweep_level": swing_low,
                        "rejection_strength": round(wick_ratio, 4),
                    }

        return default

    # ------------------------------------------------------------------

    def detect_pre_release_drift(
        self,
        symbol: str,
        minutes: int = 120,
    ) -> Dict[str, Any]:
        """Measure net directional movement over the last *minutes* minutes.

        Uses completed 1-minute candles whose ``open_time`` falls within
        the look-back window.

        Returns
        -------
        dict
            ``drift_pips``, ``drift_direction`` (``'up'``/``'down'``/
            ``'flat'``), ``candle_count``.
        """
        now_utc = datetime.now(tz=timezone.utc)
        cutoff = now_utc.replace(second=0, microsecond=0)
        # Subtract minutes manually (avoids timedelta import).
        cutoff_epoch = cutoff.timestamp() - minutes * 60

        with self._lock:
            candles = self._get_candles(symbol, "1m")
            relevant = [
                c for c in candles
                if c.open_time.timestamp() >= cutoff_epoch
            ]

        if not relevant:
            return {"drift_pips": 0.0, "drift_direction": "flat", "candle_count": 0}

        first_open = relevant[0].open
        last_close = relevant[-1].close
        pip = _pip_size(symbol)
        drift_pips = round((last_close - first_open) / pip, 1)

        if drift_pips > 0:
            direction = "up"
        elif drift_pips < 0:
            direction = "down"
        else:
            direction = "flat"

        return {
            "drift_pips": drift_pips,
            "drift_direction": direction,
            "candle_count": len(relevant),
        }

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    def flush_to_db(self, conn: sqlite3.Connection) -> int:
        """Write all un-flushed completed candles to ``candle_history``.

        Parameters
        ----------
        conn:
            An open :class:`sqlite3.Connection` (caller manages the
            lifecycle and WAL mode).

        Returns
        -------
        int
            Number of candle rows inserted.
        """
        if not self._table_ensured:
            try:
                conn.executescript(_CREATE_TABLE_SQL)
                self._table_ensured = True
            except sqlite3.Error:
                LOGGER.exception("Failed to ensure candle_history table")
                raise

        rows: list[tuple] = []

        with self._lock:
            for buf in self._completed.values():
                for candle in buf:
                    if candle.flushed:
                        continue
                    rows.append((
                        candle.symbol,
                        candle.timeframe,
                        candle.open_time.isoformat(),
                        candle.close_time.isoformat(),
                        candle.open,
                        candle.high,
                        candle.low,
                        candle.close,
                        candle.volume,
                        candle.tick_count,
                        candle.ema_20,
                        candle.ema_50,
                        candle.rsi_14,
                    ))
                    candle.flushed = True

        if not rows:
            LOGGER.debug("flush_to_db: nothing to flush")
            return 0

        try:
            conn.executemany(_INSERT_SQL, rows)
            conn.commit()
            LOGGER.info("flush_to_db: wrote %d candle(s)", len(rows))
        except sqlite3.Error:
            LOGGER.exception("flush_to_db: SQLite write failed – rolling back flushed flags")
            with self._lock:
                for buf in self._completed.values():
                    for candle in buf:
                        if candle.flushed:
                            candle.flushed = False

        return len(rows)

    # ------------------------------------------------------------------
    # Convenience / Debugging
    # ------------------------------------------------------------------

    def snapshot(self, symbol: str) -> Dict[str, list[Candle]]:
        """Return a dict mapping timeframe → list of completed candles."""
        with self._lock:
            return {
                tf: list(self._get_candles(symbol, tf))
                for tf in TIMEFRAMES
            }

    @property
    def active_keys(self) -> list[Tuple[str, str]]:
        """Return all (symbol, timeframe) pairs with a working candle."""
        with self._lock:
            return list(self._working.keys())

    def __repr__(self) -> str: # pragma: no cover
        with self._lock:
            n_working = len(self._working)
            n_completed = sum(len(d) for d in self._completed.values())
            return (
                f"<CandleAggregator working={n_working} completed={n_completed}>"
            )

    def _update_consecutive_nodes(self, symbol: str, timeframe: str) -> None:
        """Detect double/triple HVN nodes from the HVN history."""
        key = (symbol, timeframe)
        hvn_buf = self._hvn_history.get(key)
        if not hvn_buf or len(hvn_buf) < 2:
            return
        pip = _pip_size(symbol)
        tolerance_pips = 3.0
        nodes = []
        poc_list = list(hvn_buf)
        consecutive = 1
        for i in range(1, len(poc_list)):
            prev_price, _ = poc_list[i - 1]
            cur_price, _ = poc_list[i]
            distance_pips = abs(cur_price - prev_price) / pip
            if distance_pips < tolerance_pips:
                consecutive += 1
                if consecutive >= 2:
                    node_type = "TRIPLE_NODE" if consecutive >= 3 else "DOUBLE_NODE"
                    nodes.append({"price": cur_price, "type": node_type, "consecutive": consecutive})
            else:
                consecutive = 1
        self._consecutive_nodes[symbol] = nodes

    def get_consecutive_nodes(self, symbol: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._consecutive_nodes.get(symbol, []))

    def get_hvn_levels(self, symbol: str, timeframe: str = "1H", count: int = 10) -> list[float]:
        with self._lock:
            hvn_buf = self._hvn_history.get((symbol, timeframe), deque())
            return [p for p, _ in list(hvn_buf)[-count:]]
