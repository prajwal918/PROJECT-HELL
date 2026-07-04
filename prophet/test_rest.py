import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

headers = {
    "Authorization": f"Bearer {token}",
    "Deriv-App-ID": "1089"
}

# Try basic REST endpoints to verify token
urls = [
    "https://api.deriv.com/v1/ping",
    "https://api.derivws.com/v1/ping",
    "https://api.deriv.com/trading/v1/accounts",
    "https://api.binary.com/v1/ping"
]

for url in urls:
    print(f"Testing {url}...")
    try:
        r = requests.get(url, headers=headers, timeout=5)
        print(f"Status: {r.status_code}")
        print(r.text[:200])
    except Exception as e:
        print(f"Error: {e}")
