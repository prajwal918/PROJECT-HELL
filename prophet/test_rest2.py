import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

headers = {
    "Authorization": f"Bearer {token}",
    "Deriv-App-ID": "1089",
    "Content-Type": "application/json"
}

urls = [
    "https://api.derivws.com/trading/v1/accounts",
    "https://api.derivws.com/v1/accounts",
    "https://api.deriv.com/trading/v1/accounts",
    "https://api.deriv.com/v1/accounts"
]

for url in urls:
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code != 404:
            print(f"[{r.status_code}] {url}")
            print(r.text[:300])
    except Exception as e:
        pass
