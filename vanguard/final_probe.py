import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DERIV_API_TOKEN")

def final_probe():
    url = "https://api.derivws.com/trading/v1/options/accounts"
    
    # Try different header formats
    variants = [
        {"Authorization": f"Bearer {token}", "Deriv-App-ID": "1089"},
        {"Authorization": f"Bearer {token}", "Deriv-App-ID": 1089},
        {"Authorization": f"Bearer {token}", "Deriv-App-Id": "1089"},
        {"Authorization": f"Bearer {token}", "deriv-app-id": "1089"},
        {"Authorization": f"{token}", "Deriv-App-ID": "1089"},
    ]
    
    for headers in variants:
        print(f"Headers: {headers}")
        try:
            r = requests.get(url, headers=headers, timeout=5)
            print(f"Status: {r.status_code}")
            print(f"Body: {r.text}")
            if r.status_code == 200:
                print("SUCCESS!")
                return
        except:
            pass

final_probe()
