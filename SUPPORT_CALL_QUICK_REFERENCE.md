# QUICK REFERENCE: EdgeClear Support Call

## WHEN YOU CALL: **1-844-TRADE20** or **773-832-8320**

### ONE-SENTENCE ISSUE:
> "I need the correct Rithmic R|PROTOCOL API WebSocket endpoint for my paper trading account."

---

### ACCOUNT INFORMATION:
- **Username:** asdsadkiarhar6468
- **Gateway:** Rithmic 01
- **Account Type:** Paper Trading

---

### CURRENT PROBLEM:
- **Wrong URL:** `wss://rithmic.rapi.com:443` (domain doesn't exist)
- **Need:** Correct WebSocket URL for Rithmic API
- **Purpose:** Custom trading system development (Python + Rust)

---

### KEY QUESTIONS TO ASK:

1. **"What is the correct WebSocket URL for Rithmic R|PROTOCOL API?"**

2. **"Is my paper trading account enabled for API access?"**

3. **"What is the correct authentication message format?"**

4. **"How do I subscribe to MBO (Level 3) data?"**

5. **"Where can I find official API documentation?"**

---

### IF THEY ASK:

**"What platform are you using?"**
→ "Custom-built system (Python + Rust), not standard platform"

**"What's your trading volume?"**
→ "Paper trading development phase, planning live trading after testing"

**"Why do you need API access?"**
→ "Building institutional-grade trading system with Level 3 MBO data analysis"

---

### WHAT TO WRITE DOWN:

✅ **WebSocket URL:** wss://_________________:____/_______

✅ **Authentication Format:**
```json
{
  
}
```

✅ **MBO Subscription Format:**
```json
{
  
}
```

✅ **API Documentation Link:** _________________________________

✅ **Support Ticket Number:** __________________________________

---

### AFTER THE CALL:

1. **Update this file** with the information you received
2. **Test the endpoint** immediately using: `python test_correct_endpoint.py`
3. **Update the code** in: `nexus/rust-backend/src/rithmic.rs`
4. **Let me know** so I can help compile and test NEXUS

---

### IF THEY CAN'T HELP:

1. **Ask for escalation** to senior technical support
2. **Request official API documentation**
3. **Mention:** "This is blocking development of institutional trading system"
4. **Consider alternative** data providers (we can discuss)

---

**Print this page for your call!**

---

## BACKUP PLAN (IF SUPPORT FAILS):

### Alternative Data Sources:
- **OANDA API** (already used in OVERSEER)
- **Interactive Brokers API**
- **DXfeed API**
- **Polygon.io**

### What We Can Do Without Rithmic:
- ✅ Test NOVA gates 1-2 (events, bias)
- ✅ Test AEGIS logic with mock data
- ✅ Develop other system components
- ❌ Cannot test Level 3 MBO detection (gates 3)

### Timeline Impact:
- **Best case:** 1-2 days (support provides correct endpoint)
- **Medium case:** 1 week (escalation + documentation)
- **Worst case:** Switch to alternative data provider

---

**Good luck with the call! Let me know what they say.**