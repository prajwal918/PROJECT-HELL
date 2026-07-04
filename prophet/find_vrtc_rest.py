import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "")
DERIV_APP_ID = "1"

def find_vrtc():
    if not DERIV_API_TOKEN:
        print("Error: No token found")
        return

    url = "https://api.derivws.com/trading/v1/options/accounts"
    headers = {
        "Authorization": f"Bearer {DERIV_API_TOKEN}",
        "Deriv-App-ID": DERIV_APP_ID,
        "Content-Type": "application/json"
    }

    print(f"Requesting account list from {url}...")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code == 200:
            data = r.json()
            # The data structure might vary, let's look for loginids
            print("Successfully retrieved account data!")
            # Deriv API v2 usually returns an object with a 'data' list
            accounts = data.get('data', [])
            
            if not accounts:
                print("No accounts found in response data.")
                print("Raw Response:", json.dumps(data, indent=2))
                return

            for acc in accounts:
                login_id = acc.get('loginid')
                currency = acc.get('currency')
                print(f"Found: {login_id} ({currency})")
                if login_id and login_id.startswith("VRTC"):
                    print(f"RESULT_VRTC:{login_id}")
        else:
            print(f"Error: {r.status_code}")
            print("Response:", r.text)

    except Exception as e:
        print(f"Request error: {e}")

if __name__ == "__main__":
    find_vrtc()
