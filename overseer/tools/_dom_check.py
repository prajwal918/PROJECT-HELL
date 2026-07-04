import sqlite3, json
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT dom_json FROM tick_log WHERE symbol='6JM6' AND dom_json != '{}' ORDER BY rowid DESC LIMIT 1")
row = c.fetchone()
if row and row[0]:
    dom = json.loads(row[0])
    print("6JM6 DOM:")
    for b in dom.get("bids", [])[:3]:
        print(f"  BID price={b.get('price')} size={b.get('size')}")
    for a in dom.get("asks", [])[:3]:
        print(f"  ASK price={a.get('price')} size={a.get('size')}")
else:
    print("No DOM data for 6JM6")

c.execute("SELECT dom_json FROM tick_log WHERE symbol='6EM6' AND dom_json != '{}' ORDER BY rowid DESC LIMIT 1")
row = c.fetchone()
if row and row[0]:
    dom = json.loads(row[0])
    print("\n6EM6 DOM:")
    for b in dom.get("bids", [])[:3]:
        print(f"  BID price={b.get('price')} size={b.get('size')}")
    for a in dom.get("asks", [])[:3]:
        print(f"  ASK price={a.get('price')} size={a.get('size')}")
conn.close()
