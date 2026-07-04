import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

def probe():
    print(f"Probing with token: {token[:10]}...")
    
    headers_variants = [
        {"Authorization": f"Bearer {token}", "Deriv-App-ID": "1089"},
        {"Authorization": f"Bearer {token}", "Deriv-App-ID": "1"},
        {"Authorization": f"Bearer {token}"},
        {"Authorization": token, "Deriv-App-ID": "1089"},
        {"X-Deriv-Token": token, "Deriv-App-ID": "1089"},
        {"token": token, "Deriv-App-ID": "1089"}
    ]
    
    urls = [
        "https://api.derivws.com/trading/v1/options/accounts",
        "https://api.derivws.com/trading/v1/accounts",
        "https://api.deriv.com/trading/v1/options/accounts"
    ]
    
    for url in urls:
        for headers in headers_variants:
            print(f"URL: {url}")
            print(f"Headers: { {k:v[:5]+'...' for k,v in headers.items()} }")
            try:
                r = requests.get(url, headers=headers, timeout=5)
                print(f"Result: {r.status_code}")
                if r.status_code == 200:
                    print("SUCCESS!")
                    print(r.text)
                    return
            except:
                pass
            print("-" * 20)

probe()
