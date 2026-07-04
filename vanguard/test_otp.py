import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

headers = {
    "Authorization": f"Bearer {token}",
    "Deriv-App-ID": "1089",
    "Content-Type": "application/json"
}

url = "https://api.derivws.com/trading/v1/options/accounts/CR12345/otp"

print(f"Testing {url}...")
try:
    r = requests.post(url, headers=headers, timeout=5)
    print(f"Status: {r.status_code}")
    print(r.text[:500])
except Exception as e:
    print(f"Error: {e}")
