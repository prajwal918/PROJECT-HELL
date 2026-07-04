"""OVERSEER v12 Web Dashboard — lightweight HTTP status page.

Serves a single-page dashboard on ``DASHBOARD_PORT`` (default 8080)
showing live trading stats, recent trades, signal journal, risk status,
order flow analysis, and P&L.

Run standalone:
    python -m core.dashboard

Or auto-started by main.py when DASHBOARD_ENABLED=true.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from database.setup_db import DB_PATH

DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
DASHBOARD_DB_TIMEOUT = float(os.getenv("DASHBOARD_DB_TIMEOUT", "1.0"))
DASHBOARD_CACHE_SECONDS = float(os.getenv("DASHBOARD_CACHE_SECONDS", "2.0"))

_STATS_CACHE: dict[str, Any] = {"time": 0.0, "payload": None}

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OVERSEER v12</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}
h1{color:#58a6ff;font-size:1.5rem;margin-bottom:4px}
.subtitle{color:#8b949e;font-size:0.85rem;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:24px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
.card-label{color:#8b949e;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.5px}
.card-value{font-size:1.4rem;font-weight:700;margin-top:4px}
.card-value.positive{color:#3fb950}
.card-value.negative{color:#f85149}
.card-value.neutral{color:#58a6ff}
.card-value.warning{color:#d29922}
.status-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
.status-dot.live{background:#3fb950;animation:pulse 2s infinite}
.status-dot.halted{background:#f85149}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
table{width:100%;border-collapse:collapse;font-size:0.8rem}
th{text-align:left;color:#8b949e;border-bottom:1px solid #30363d;padding:6px 4px;font-weight:500;white-space:nowrap}
td{padding:6px 4px;border-bottom:1px solid #21262d;white-space:nowrap}
tr:hover{background:#161b22}
.buy{color:#3fb950}
.sell{color:#f85149}
.section-title{color:#c9d1d9;font-size:1.05rem;font-weight:600;margin-bottom:10px;margin-top:20px;display:flex;align-items:center;gap:8px}
.section-title .badge{background:#30363d;color:#8b949e;font-size:0.7rem;padding:2px 8px;border-radius:10px}
.refresh-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
#clock{color:#8b949e;font-size:0.85rem}
.tab-bar{display:flex;gap:0;margin-bottom:16px;border-bottom:1px solid #30363d}
.tab{padding:8px 16px;cursor:pointer;color:#8b949e;font-size:0.85rem;border-bottom:2px solid transparent}
.tab.active{color:#58a6ff;border-bottom-color:#58a6ff}
.tab:hover{color:#c9d1d9}
.tab-content{display:none}
.tab-content.active{display:block}
.fw-bar{height:6px;border-radius:3px;background:#21262d;min-width:40px;display:inline-block;vertical-align:middle;margin-left:6px}
.fw-bar-fill{height:100%;border-radius:3px;background:#58a6ff}
.l3-tag{display:inline-block;padding:1px 5px;border-radius:3px;font-size:0.7rem;margin-right:3px}
.l3-tag.on{background:#1a3a2a;color:#3fb950}
.l3-tag.off{background:#2a1a1a;color:#484848}
.outcome{font-weight:700;font-size:0.75rem}
.outcome.win{color:#3fb950}
.outcome.loss{color:#f85149}
.outcome.flat{color:#8b949e}
.signal-expand{cursor:pointer;color:#58a6ff;font-size:0.75rem}
.detail-row{display:none;background:#0d1117}
.detail-row.open{display:table-row}
.detail-cell{padding:8px;font-size:0.75rem;color:#8b949e}
@media(max-width:600px){.grid{grid-template-columns:1fr 1fr}.card-value{font-size:1.1rem}}
</style>
</head>
<body>
<h1>OVERSEER v12</h1>
<p class="subtitle">Real-time Forex Trading System &mdash; Signal Journal + Order Flow</p>
<div class="refresh-bar">
<div id="status-indicator"></div>
<div id="clock"></div>
</div>
<div class="grid" id="stats-grid"></div>

  <div class="tab-bar">
  <div class="tab active" data-tab="binary">&#9889; BINARY</div>
  <div class="tab" data-tab="signals">Signal Journal</div>
  <div class="tab" data-tab="trades">Executed Trades</div>
  <div class="tab" data-tab="flow">Order Flow</div>
  </div>

  <div class="tab-content active" id="tab-binary">
  <div style="display:flex;align-items:center;gap:15px;margin-bottom:15px;">
  <h2 style="color:#00ff88;margin:0;font-size:22px;">&#9889; BINARY SIGNALS</h2>
  <span id="bin-regime" style="color:#888;font-size:13px;background:#1a1a1a;padding:4px 10px;border-radius:4px;">Loading...</span>
  <span style="color:#555;font-size:12px;">1-Min Order Flow &bull; Auto-Refresh 5s</span>
  </div>
  <div id="binary-stats" style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap;"></div>
  <div id="binary-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;">
  <div style="color:#444;padding:30px;text-align:center;font-size:13px;">Scanning order flow...</div>
  </div>
  <div style="margin-top:20px;">
  <div class="section-title">Last 10 Binary Outcomes</div>
  <table><thead><tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Prob</th><th>Expiry</th><th>Outcome</th><th>Pips</th></tr></thead><tbody id="binary-history"></tbody></table>
  </div>
  </div>

<div class="tab-content active" id="tab-signals">
<table>
<thead><tr><th>#</th><th>Time</th><th>Symbol</th><th>Dir</th><th>Score</th><th>Adj</th><th>Exec</th><th>Spread</th><th>Regime</th><th>Session</th><th>10t</th><th>50t</th><th>200t</th><th></th></tr></thead>
<tbody id="signals-body"></tbody>
</table>
</div>

<div class="tab-content" id="tab-trades">
<table>
<thead><tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Reason</th></tr></thead>
<tbody id="trades-body"></tbody>
</table>
</div>

<div class="tab-content" id="tab-flow">
<div class="section-title">L3 Feature Summary (last 50 signals) <span class="badge" id="flow-count">0</span></div>
<div class="grid" id="flow-grid"></div>
<div class="section-title" style="margin-top:16px">Per-Symbol Breakdown</div>
<table>
<thead><tr><th>Symbol</th><th>Signals</th><th>Avg Score</th><th>P&L</th></tr></thead>
<tbody id="symbol-body"></tbody>
</table>
</div>

<script>
const PIP=0.0001;
function fmtP(p){return p!=null?p.toFixed(5):'—'}
function fmtPnl(p){if(p==null)return'—';const v=p.toFixed(2);return p>=0?'+'+v:v}
function pnlC(p){if(p==null)return'';return p>0?'positive':p<0?'negative':'neutral'}
function fmtT(t){if(!t)return'—';return t.replace('T',' ').substring(11,19)}
function fmtD(t){if(!t)return'—';return t.replace('T',' ').substring(5,19)}
function fmtS(s){return s!=null?s.toFixed(4):'—'}
function ocCls(o){if(!o)return'';return o.toLowerCase()}
function mkTag(label,val,threshold){const on=Math.abs(val)>=threshold;return`<span class="l3-tag ${on?'on':'off'}">${label}</span>`}

function renderFW(fw){
 if(!fw)return'';
 const fwNames=Object.keys(fw).sort();
 let h='<table style="font-size:0.7rem;border:none">';
 for(const n of fwNames){
  const v=fw[n];const pct=Math.round(v*100);
  h+=`<tr style="border:none"><td style="border:none;color:#8b949e;padding:1px 4px">${n.replace('FW','')}</td><td style="border:none;padding:1px 4px">${pct}%</td><td style="border:none;padding:1px 4px"><div class="fw-bar" style="width:60px"><div class="fw-bar-fill" style="width:${pct}%"></div></div></td></tr>`;
 }
 return h+'</table>';
}

function renderL3(l3){
 if(!l3)return'';
 const items=[
        ['Spoof',l3.spoof_reversal_signal||l3.spoof_signal,0.5],['Queue',l3.queue_exhaustion_signal||l3.queue_exhaustion,0.5],
        ['Ice',l3.iceberg_detected||l3.iceberg_signal,0.5],['Adv',l3.adverse_selection_risk||l3.adverse_risk,0.2],
        ['HFT',l3.hft_cluster_detected||l3.hft_signal,0.5],['Vac',l3.liquidity_vacuum_signal||l3.vacuum_signal,0.5],
 ];
 return items.map(i=>mkTag(i[0],i[1],i[2])).join(' ');
}

function renderBias(b){
 if(!b)return'';
 const parts=[];
 if(b.spoof_bias)parts.push('spf:'+b.spoof_bias.toFixed(3));
 if(b.queue_bias)parts.push('que:'+b.queue_bias.toFixed(3));
 if(b.iceberg_bias)parts.push('ice:'+b.iceberg_bias.toFixed(3));
 if(b.adverse_bias)parts.push('adv:'+b.adverse_bias.toFixed(3));
 if(b.hft_bias)parts.push('hft:'+b.hft_bias.toFixed(3));
 if(b.vacuum_bias)parts.push('vac:'+b.vacuum_bias.toFixed(3));
 if(b.iv_bias)parts.push('iv:'+b.iv_bias.toFixed(3));
 return parts.length?'+'+parts.join(' '):'none';
}

let expandedRows=new Set();

async function refresh(){
try{
const r=await fetch('/api/stats');const d=await r.json();
let statusHTML='';
if(d.halted){statusHTML='<span class="status-dot halted"></span>HALTED — '+d.halt_reason}
else{statusHTML='<span class="status-dot live"></span>LIVE'}
document.getElementById('status-indicator').innerHTML=statusHTML;

const wr=d.total_trades>0?(d.wins/d.total_trades*100).toFixed(1)+'%':'—';
const sg=d.signal_stats||{};
const grid=document.getElementById('stats-grid');
grid.innerHTML=[
{l:'Signals',v:sg.total_signals||0,c:'neutral'},
{l:'Executed',v:sg.executed_count||0,c:'neutral'},
{l:'Signal P&L',v:'$'+fmtPnl(sg.total_pnl),c:pnlC(sg.total_pnl)},
{l:'Avg Score',v:fmtS(sg.avg_score),c:'neutral'},
{l:'10t Win%',v:(sg.outcome_10_wr||0)+'%',c:(sg.outcome_10_wr||0)>=55?'positive':'warning'},
{l:'50t Win%',v:(sg.outcome_50_wr||0)+'%',c:(sg.outcome_50_wr||0)>=55?'positive':'warning'},
{l:'200t Win%',v:(sg.outcome_200_wr||0)+'%',c:(sg.outcome_200_wr||0)>=55?'positive':'warning'},
{l:'Total P&L',v:'$'+fmtPnl(d.total_pnl),c:pnlC(d.total_pnl)},
{l:'Trade WR',v:wr,c:d.total_trades>0&&d.wins/d.total_trades>=0.5?'positive':'warning'},
{l:'Trades Today',v:d.daily_trades,c:'neutral'},
].map(x=>'<div class="card"><div class="card-label">'+x.l+'</div><div class="card-value '+x.c+'">'+x.v+'</div></div>').join('');

const sbody=document.getElementById('signals-body');
sbody.innerHTML=(d.recent_signals||[]).map(s=>{
 const dc=s.direction==='BUY'?'buy':'sell';
 const execTag=s.executed?'<span class="l3-tag on">LIVE</span>':'<span class="l3-tag off">SIG</span>';
 const o10=s.outcome_10?`<span class="outcome ${ocCls(s.outcome_10)}">${s.outcome_10}</span>`:'—';
 const o50=s.outcome_50?`<span class="outcome ${ocCls(s.outcome_50)}">${s.outcome_50}</span>`:'—';
 const o200=s.outcome_200?`<span class="outcome ${ocCls(s.outcome_200)}">${s.outcome_200}</span>`:'—';
 const isExp=expandedRows.has(s.id);
 return`<tr><td>${s.id}</td><td>${fmtD(s.timestamp)}</td><td>${s.symbol}</td><td class="${dc}">${s.direction}</td><td>${fmtS(s.score)}</td><td>${fmtS(s.adjusted_score)}</td><td>${execTag}</td><td>${s.spread_bps!=null?s.spread_bps.toFixed(1):'—'}</td><td>${s.risk_regime||'—'}</td><td>${s.session||'—'}</td><td>${o10}</td><td>${o50}</td><td>${o200}</td><td><span class="signal-expand" onclick="toggleDetail(${s.id})">${isExp?'−':'+'}</span></td></tr>`+
 `<tr class="detail-row ${isExp?'open':''}" id="detail-${s.id}"><td colspan="14" class="detail-cell"><div style="display:flex;gap:24px;flex-wrap:wrap"><div><b>Framework Scores</b>${renderFW(s.framework_scores)}</div><div><b>L3 Order Flow</b><br>${renderL3(s.l3_features)}</div><div><b>Bias</b><br>${renderBias(s.bias_breakdown)}</div></div></td></tr>`;
}).join('');

const tbody=document.getElementById('trades-body');
tbody.innerHTML=(d.recent_trades||[]).map(t=>{
 const dc=t.direction==='BUY'?'buy':'sell';
 return'<tr><td>'+fmtD(t.timestamp)+'</td><td>'+t.symbol+'</td><td class="'+dc+'">'+t.direction+'</td><td>'+fmtP(t.entry_price)+'</td><td>'+fmtP(t.exit_price)+'</td><td class="'+pnlC(t.pnl)+'">'+fmtPnl(t.pnl)+'</td><td>'+(t.close_reason||'open')+'</td></tr>'
}).join('');

const flowGrid=document.getElementById('flow-grid');
const l3=(d.l3_summary||{});
flowGrid.innerHTML=[
{l:'Spoof Signals',v:l3.spoof_count||0,c:'warning'},
{l:'Queue Exhaust',v:l3.queue_count||0,c:'warning'},
{l:'Iceberg Det.',v:l3.iceberg_count||0,c:'neutral'},
{l:'Adverse Risk',v:l3.adverse_count||0,c:'negative'},
{l:'HFT Clusters',v:l3.hft_count||0,c:'neutral'},
{l:'Vacuum Events',v:l3.vacuum_count||0,c:'negative'},
].map(x=>'<div class="card"><div class="card-label">'+x.l+'</div><div class="card-value '+x.c+'">'+x.v+'</div></div>').join('');
document.getElementById('flow-count').textContent=sg.total_signals||0;

const symBody=document.getElementById('symbol-body');
symBody.innerHTML=(sg.by_symbol||[]).map(s=>{
 return`<tr><td>${s.symbol}</td><td>${s.count}</td><td>${fmtS(s.avg_score)}</td><td class="${pnlC(s.pnl)}">${fmtPnl(s.pnl)}</td></tr>`;
}).join('');

}catch(e){console.error(e)}
document.getElementById('clock').textContent=new Date().toLocaleString();
}

function toggleDetail(id){
 if(expandedRows.has(id)){expandedRows.delete(id)}else{expandedRows.add(id)}
 const row=document.getElementById('detail-'+id);
 if(row){row.classList.toggle('open')}
 const expander=document.querySelector(`tr td .signal-expand[onclick="toggleDetail(${id})"]`);
 if(expander){expander.textContent=expandedRows.has(id)?'−':'+'}
}

  document.querySelectorAll('.tab').forEach(t=>{
  t.addEventListener('click',()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(x=>x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('tab-'+t.dataset.tab).classList.add('active');
  });
  });

  async function loadBinary(){
  try{
  const r=await fetch('/api/binary');
  const d=await r.json();
  const sigs=d.signals||[];
  const stats=d.stats||{};
  const grid=document.getElementById('binary-grid');
  const regime=document.getElementById('bin-regime');
  const statsEl=document.getElementById('binary-stats');
  const now=new Date();
  const utcStr=now.toISOString().slice(11,19);
  regime.textContent=sigs.length>0?stats.regime+' \u2022 '+stats.regime_name+' \u2022 UTC '+utcStr:'UTC '+utcStr+' \u2022 '+stats.regime+' '+stats.regime_name;
  if(stats.regime_tradeable===false){
  grid.innerHTML='<div style="color:#444;padding:30px;text-align:center;font-size:13px;grid-column:1/-1;">No active 1-minute signals &mdash; Market closed or weak flow ('+stats.regime_name+')</div>';
  }else if(!sigs.length){
  grid.innerHTML='<div style="color:#444;padding:30px;text-align:center;font-size:13px;grid-column:1/-1;">No active 1-minute signals &mdash; Scanning order flow...</div>';
  }else{
  grid.innerHTML=sigs.map(s=>{
  const isUp=s.dir==='BUY';
  const border=isUp?(s.cls==='strong'?'#00ff88':'#00cc66'):(s.cls==='strong'?'#ff4444':'#cc3333');
  const glow=isUp?'rgba(0,255,136,0.12)':'rgba(255,68,68,0.12)';
  const deltaSign=s.delta>0?'+':'';
  return '<div style="background:#111;border:2px solid '+border+';border-radius:10px;padding:16px;text-align:center;box-shadow:0 0 15px '+glow+';">'
  +'<div style="color:#888;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">'+s.symbol+' &bull; '+s.regime+'</div>'
  +'<div style="font-size:42px;line-height:1;margin:8px 0;color:'+border+';">'+s.arrow+'</div>'
  +'<div style="font-size:36px;font-weight:900;color:'+border+';margin:4px 0;">'+s.prob+'%</div>'
  +'<div style="font-size:14px;font-weight:700;color:'+border+';text-transform:uppercase;margin:4px 0;">'+s.label+'</div>'
  +'<div style="margin-top:10px;display:flex;justify-content:center;gap:10px;font-size:11px;color:#666;">'
  +'<span style="background:#1a1a1a;padding:3px 8px;border-radius:3px;color:#ffaa00;">'+s.expiry+'</span>'
  +'<span>Spd '+s.spread+'</span>'
  +'<span>\u0394 '+deltaSign+s.delta+'</span>'
  +'</div>'
  +'<div style="margin-top:6px;font-size:10px;color:#333;">'+s.time+' UTC</div>'
  +'</div>';
  }).join('');
  }
  }catch(e){
  document.getElementById('binary-grid').innerHTML='<div style="color:#444;padding:30px;text-align:center;font-size:13px;grid-column:1/-1;">Binary engine offline</div>';
  }
  }

  refresh();loadBinary();setInterval(refresh,5000);setInterval(loadBinary,5000);
</script>
</body>
</html>"""


_DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")


class _DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if _DASHBOARD_API_KEY:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {_DASHBOARD_API_KEY}":
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Bearer realm="OVERSEER"')
                self.end_headers()
                return
        if self.path == "/" or self.path == "/index.html":
            self._serve_html()
        elif self.path == "/api/stats":
            self._serve_stats()
        elif self.path == "/api/signals":
            self._serve_signals()
        elif self.path == "/api/binary":
            self._serve_binary()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_html(self) -> None:
        data = _DASHBOARD_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_stats(self) -> None:
        payload = _fetch_dashboard_data()
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _serve_signals(self) -> None:
        payload = _fetch_signal_data()
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _serve_binary(self) -> None:
        try:
            from core.binary_signals import get_all_binary_signals, get_binary_stats
            signals = get_all_binary_signals()
            stats = get_binary_stats()
            payload = {"signals": signals, "stats": stats}
        except Exception as e:
            payload = {"signals": [], "stats": {}, "error": str(e)}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def _fetch_signal_data() -> dict[str, Any]:
    try:
        from ml.signal_logger import get_recent_signals, get_signal_stats
        conn = _open_read_conn()
        stats = get_signal_stats(conn)
        recent = get_recent_signals(conn, limit=50)
        conn.close()
        return {"signal_stats": stats, "recent_signals": recent}
    except Exception:
        return {"signal_stats": {}, "recent_signals": []}


def _fetch_l3_summary(conn: sqlite3.Connection) -> dict[str, int]:
    try:
        row = conn.execute(
            """
        SELECT
        COUNT(CASE WHEN l3_features_json LIKE '%spoof_reversal_signal": 1%' OR l3_features_json LIKE '%spoof_signal": 1%' THEN 1 END),
        COUNT(CASE WHEN l3_features_json LIKE '%queue_exhaustion_signal": 1%' OR l3_features_json LIKE '%queue_exhaustion": 1%' THEN 1 END),
        COUNT(CASE WHEN l3_features_json LIKE '%iceberg_detected": 1%' OR l3_features_json LIKE '%iceberg_signal": 1%' THEN 1 END),
        COUNT(CASE WHEN (l3_features_json LIKE '%adverse_selection_risk": %' AND l3_features_json NOT LIKE '%adverse_selection_risk": 0%') OR (l3_features_json LIKE '%adverse_risk": %' AND l3_features_json NOT LIKE '%adverse_risk": 0%') THEN 1 END),
        COUNT(CASE WHEN l3_features_json LIKE '%hft_cluster_detected": 1%' OR l3_features_json LIKE '%hft_signal": 1%' THEN 1 END),
        COUNT(CASE WHEN l3_features_json LIKE '%liquidity_vacuum_signal": 1%' OR l3_features_json LIKE '%vacuum_signal": 1%' THEN 1 END)
            FROM (
                SELECT l3_features_json
                FROM signal_log
                ORDER BY id DESC
                LIMIT 50
            )
            """
        ).fetchone()
        return {
            "spoof_count": row[0] if row else 0,
            "queue_count": row[1] if row else 0,
            "iceberg_count": row[2] if row else 0,
            "adverse_count": row[3] if row else 0,
            "hft_count": row[4] if row else 0,
            "vacuum_count": row[5] if row else 0,
        }
    except Exception:
        return {
            "spoof_count": 0, "queue_count": 0, "iceberg_count": 0,
            "adverse_count": 0, "hft_count": 0, "vacuum_count": 0,
        }


def _fetch_dashboard_data() -> dict[str, Any]:
    now = time.monotonic()
    cached = _STATS_CACHE.get("payload")
    if cached is not None and now - float(_STATS_CACHE.get("time", 0.0)) < DASHBOARD_CACHE_SECONDS:
        return cached

    try:
        conn = _open_read_conn()
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_trades,
                COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(pnl), 0) AS total_pnl,
                COALESCE(SUM(CASE WHEN date(timestamp) = date('now') THEN pnl ELSE 0 END), 0) AS daily_pnl,
                COALESCE(SUM(CASE WHEN timestamp >= datetime('now', '-7 days') THEN pnl ELSE 0 END), 0) AS weekly_pnl,
                COALESCE(SUM(CASE WHEN date(timestamp) = date('now') THEN 1 ELSE 0 END), 0) AS daily_trades,
                COALESCE(AVG(pnl), 0) AS avg_pnl,
                COALESCE(MAX(pnl), 0) AS best_trade,
                COALESCE(MIN(pnl), 0) AS worst_trade
            FROM trade_executions
            WHERE exit_price IS NOT NULL
            """
        ).fetchone()

        halted_row = conn.execute("SELECT is_halted, halt_reason FROM system_status WHERE id = 1").fetchone()

        recent = conn.execute(
            """
            SELECT timestamp, symbol, direction, entry_price, exit_price, pnl, close_reason
            FROM trade_executions
            ORDER BY trade_id DESC LIMIT 25
            """
        ).fetchall()

        signal_stats = {}
        recent_signals = []
        l3_summary = {}
        try:
            from ml.signal_logger import get_signal_stats, get_recent_signals
            signal_stats = get_signal_stats(conn)
            recent_signals = get_recent_signals(conn, limit=50)
            l3_summary = _fetch_l3_summary(conn)
        except Exception:
            pass

        conn.close()

        total = row[0] if row else 0
        wins = row[1] if row else 0
        recent_trades = [
            {
                "timestamp": r[0],
                "symbol": r[1],
                "direction": r[2],
                "entry_price": r[3],
                "exit_price": r[4],
                "pnl": r[5],
                "close_reason": r[6],
            }
            for r in recent
        ]

        payload = {
            "total_trades": total,
            "wins": wins,
            "losses": total - wins,
            "total_pnl": round(row[2], 2) if row else 0,
            "daily_pnl": round(row[3], 2) if row else 0,
            "weekly_pnl": round(row[4], 2) if row else 0,
            "daily_trades": row[5] if row else 0,
            "avg_pnl": round(row[6], 2) if row else 0,
            "best_trade": round(row[7], 2) if row else 0,
            "worst_trade": round(row[8], 2) if row else 0,
            "halted": bool(halted_row[0]) if halted_row else False,
            "halt_reason": halted_row[1] if halted_row else None,
            "recent_trades": recent_trades,
            "signal_stats": signal_stats,
            "recent_signals": recent_signals,
            "l3_summary": l3_summary,
        }
        _STATS_CACHE["time"] = now
        _STATS_CACHE["payload"] = payload
        return payload
    except Exception:
        if cached is not None:
            return cached
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "total_pnl": 0, "daily_pnl": 0, "weekly_pnl": 0,
            "daily_trades": 0, "avg_pnl": 0, "best_trade": 0, "worst_trade": 0,
            "halted": False, "halt_reason": None, "recent_trades": [],
            "signal_stats": {}, "recent_signals": [], "l3_summary": {},
        }


def _open_read_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=DASHBOARD_DB_TIMEOUT)
    conn.execute("PRAGMA busy_timeout = 1000")
    conn.execute("PRAGMA query_only = ON")
    return conn


def start_dashboard(port: int = DASHBOARD_PORT) -> HTTPServer:
    bind_addr = os.getenv("DASHBOARD_BIND", "127.0.0.1")
    server = ThreadingHTTPServer((bind_addr, port), _DashboardHandler)
    return server


if __name__ == "__main__":
    srv = start_dashboard()
    print(f"OVERSEER dashboard: http://localhost:{DASHBOARD_PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.server_close()
