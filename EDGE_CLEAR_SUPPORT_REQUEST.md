# EDGE CLEAR SUPPORT REQUEST
## Rithmic Paper Trading API Connection Issue

**Date:** June 23, 2026
**Account:** asdsadkiarhar6468 (Paper Trading)
**Gateway:** Rithmic 01
**Support Contact:** 1-844-TRADE20 | 773-832-8320

---

## ISSUE SUMMARY
Cannot establish WebSocket connection to Rithmic API for paper trading account. Current endpoint `wss://rithmic.rapi.com:443` does not exist.

---

## QUESTIONS FOR EDGE CLEAR SUPPORT

### 1. Rithmic WebSocket API Endpoint
**What is the correct WebSocket URL for Rithmic R|PROTOCOL API?**
- Current attempt: `wss://rithmic.rapi.com:443` (fails - domain does not exist)
- Need: Correct WebSocket endpoint for paper trading
- Protocol: WebSocket + JSON (per Rithmic documentation)

### 2. Paper Trading API Access
**Is our paper trading account enabled for API access?**
- Account: asdsadkiarhar6468
- Gateway: Rithmic 01
- Need confirmation: API permissions enabled

### 3. Authentication Format
**What is the correct authentication message format for Rithmic WebSocket API?**
- Current attempt:
```json
{
  "user": "asdsadkiarhar6468",
  "password": "fd1135d1",
  "gateway": "Rithmic 01",
  "app_name": "NEXUS",
  "app_version": "2.0.0",
  "requestId": 1
}
```
- Need: Correct authentication format and required fields

### 4. MBO Data Subscription
**How to subscribe to Market By Order (MBO) Level 3 data via WebSocket API?**
- Target: EUR/USD forex pair (or available paper trading symbols)
- Need: Subscription message format and parameters

### 5. Documentation Access
**Where can we find official Rithmic R|PROTOCOL API documentation?**
- Current: No public WebSocket API documentation available
- Need: Official API docs, examples, connection guide

### 6. Paper Trading Limitations
**Are there any limitations or differences for paper trading API vs live trading?**
- Market hours
- Data availability
- Symbol list
- Rate limits

---

## TECHNICAL DETAILS TO PROVIDE SUPPORT

### Environment
- **Operating System:** Windows 10/11 (development), Linux (production)
- **Programming Languages:** Python 3.12, Rust 1.70+
- **WebSocket Libraries:** 
  - Python: `websockets` library
  - Rust: `tokio-tungstenite` library

### Network Status
- ✅ DNS resolution: `rithmic.com` works (185.230.63.107)
- ✅ TCP connectivity: Ports 80 and 443 accessible
- ❌ WebSocket endpoint: `rithmic.rapi.com` does not exist
- ❌ API documentation: Not publicly available

### Connection Attempts Tried
1. `wss://rithmic.rapi.com:443` → Domain does not exist
2. `wss://api.rithmic.com:443` → Domain does not exist  
3. `wss://rithmic.com:443` → Redirects to website (not WebSocket API)
4. `wss://rithmic.com:443/ws` → Redirects to website
5. `wss://rithmic.com:443/api` → Redirects to website

### Error Messages
- **DNS Error:** `[Errno 11001] getaddrinfo failed` (for rithmic.rapi.com)
- **Connection Error:** `Redirects to https://www.rithmic.com/` (for rithmic.com)

---

## PROJECT CONTEXT

### What We're Building
**PROJECT HELL** - Institutional-grade trading system with 5 integrated projects:
- **NOVA:** 1-min binary options (news-driven)
- **AEGIS:** 15-min binary options (MBO absorption)
- **NEXUS:** Rust data pipeline (Rithmic integration)
- **OVERSEER:** Forex system (152 gates)
- **VANGUARD:** Binary signal system

### Why We Need Rithmic API
- **Level 3 MBO Data:** For NOVA/AEGIS L3 detection gates
- **Low Latency:** Direct exchange connection required
- **Unlimited Depth:** Full order book visibility
- **Paper Trading:** Development and testing environment

### Current Architecture
```
Rithmic API (WebSocket)
    ↓
NEXUS (Rust Backend)
    ↓ WebSocket (localhost:9001)
NOVA + AEGIS (Python Trading Logic)
```

---

## EXPECTED SUPPORT RESPONSE

### Minimum Information Needed
1. **Correct WebSocket URL:** `wss://[correct-domain]:[port]/[path]`
2. **Authentication Format:** Example login message
3. **MBO Subscription Format:** Example subscription message
4. **API Documentation:** Link to official docs
5. **Paper Trading Symbol List:** Available instruments

### Ideal Additional Information
1. **Rate Limits:** Requests per second/minute
2. **Reconnection Procedure:** How to handle disconnections
3. **Data Format:** Example tick/MBO message structure
4. **Market Hours:** Paper trading availability
5. **Troubleshooting Guide:** Common connection issues

---

## CONTACT PREFERENCES

### Primary Contact Method
- **Phone:** 1-844-TRADE20 or 773-832-8320
- **Hours:** 24/7 (per EdgeClear website)
- **Priority:** High (blocking development)

### Alternative Methods
- **Email:** [Check EdgeClear website for support email]
- **Live Chat:** [Check EdgeClear website for chat support]
- **Account Portal:** https://rithmic.com/console

### Information to Provide When Calling
1. Account number: asdsadkiarhar6468
2. Gateway: Rithmic 01
3. Issue: "Rithmic R|PROTOCOL API WebSocket endpoint for paper trading"
4. Technical context: "Building trading system, need Level 3 MBO data access"
5. Urgency: "Blocking development - need correct API endpoint"

---

## FOLLOW-UP QUESTIONS (IF INITIAL RESPONSE UNCLEAR)

### If They Ask About Platform
- **Question:** "What trading platform are you using?"
- **Answer:** "Custom-built system (Python + Rust), not using standard platform"

### If They Ask About Purpose
- **Question:** "What is the purpose of API access?"
- **Answer:** "Institutional-grade trading system development for paper trading testing"

### If They Mention Standard Platforms
- **Question:** "Have you tried [Platform Name]?"
- **Answer:** "We need direct API access for custom algorithm development, not standard platform"

### If They Ask About Budget
- **Question:** "What is your trading volume/budget?"
- **Answer:** "Currently in paper trading development phase, planning for live trading after testing"

---

## NEXT STEPS AFTER SUPPORT CONTACT

### Immediate Actions
1. **Document Response:** Record all information provided by EdgeClear
2. **Update Configuration:** Modify `.env.rithmic` with correct endpoint
3. **Update Code:** Fix WebSocket URL in `nexus/rust-backend/src/rithmic.rs`
4. **Test Connection:** Run updated connection test

### If Successful
1. **Compile NEXUS:** Build Rust backend with correct endpoint
2. **Test Data Flow:** Verify MBO data reception
3. **Start NOVA/AEGIS:** Begin paper trading testing
4. **Monitor Performance:** Check latency and data quality

### If Unsuccessful
1. **Request Escalation:** Ask for senior technical support
2. **Request Documentation:** Insist on official API documentation
3. **Consider Alternatives:** Explore other data providers
4. **Update Project Plan:** Adjust timeline based on API availability

---

## SUPPORT CALL CHECKLIST

### Before Calling
- [ ] Have account number ready: asdsadkiarhar6468
- [ ] Have gateway information: Rithmic 01
- [ ] Prepare technical context: Custom Python + Rust system
- [ ] Note urgency: Blocking development
- [ ] Have pen/paper ready to document response

### During Call
- [ ] Clearly state: "Need Rithmic R|PROTOCOL API WebSocket endpoint for paper trading"
- [ ] Mention: "Current endpoint rithmic.rapi.com does not exist"
- [ ] Ask for: "Correct WebSocket URL and authentication format"
- [ ] Request: "Official API documentation"
- [ ] Document: All information provided

### After Call
- [ ] Update this document with support response
- [ ] Test provided endpoint immediately
- [ ] Update project configuration files
- [ ] Notify team of resolution status
- [ ] Plan next development steps

---

## EMERGENCY ALTERNATIVES (IF SUPPORT UNRESPONSIVE)

### Alternative Data Providers
1. **Interactive Brokers** - Has API, may support forex
2. **OANDA** - Forex API, already used in OVERSEER
3. **DXfeed** - Market data API, supports multiple instruments
4. **Polygon.io** - Real-time and historical data
5. **Alpaca** - Stock and crypto API (may not support forex)

### Temporary Workaround
1. **Use OVERSEER data** - MotiveWave feed for initial testing
2. **Simulated data** - Enhanced mock data for development
3. **Delayed Rithmic integration** - Focus on other components first

### Project Impact
- **Timeline:** May delay NOVA/AEGIS L3 features
- **Functionality:** Can test other gates (events, bias) without L3
- **Quality:** Paper trading testing delayed until API resolved

---

**Document Status:** Ready for Support Contact
**Priority:** HIGH - Blocking Development
**Expected Resolution:** 1-2 business days (per EdgeClear 24/7 support)