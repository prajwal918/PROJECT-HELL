import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

def broad_probe():
    print(f"Broad probing with token: {token[:15]}...")
    
    # Common App IDs for Deriv
    app_ids = ["1", "1089", "16929", "19111", "21156"]
    
    # Possible endpoints
    urls = [
        "https://api.derivws.com/trading/v1/options/accounts",
        "https://api.derivws.com/trading/v1/accounts",
        "https://api.deriv.com/trading/v1/options/accounts",
        "https://api.deriv.com/v1/accounts",
        "https://api.binary.com/v1/accounts",
        "https://api.derivws.com/v1/accounts"
    ]
    
    for url in urls:
        for app_id in app_ids:
            headers = {
                "Authorization": f"Bearer {token}",
                "Deriv-App-ID": app_id,
                "Content-Type": "application/json"
            }
            try:
                r = requests.get(url, headers=headers, timeout=5)
                if r.status_code == 200 and "loginid" in r.text:
                    print(f"✅ SUCCESS! URL: {url} | AppID: {app_id}")
                    print(r.text)
                    return
                elif r.status_code != 404:
                    print(f"[{r.status_code}] URL: {url} | AppID: {app_id} | {r.text[:50]}")
            except:
                pass

broad_probe()
