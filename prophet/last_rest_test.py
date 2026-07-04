import requests
import json

def test_rest():
    token = "pat_f0137fefe3092d476468e51af5e3f69bd78168ae6530949f45daaf608bc68e58"
    url = "https://api.derivws.com/trading/v1/options/accounts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Deriv-App-ID": "1089",
        "Content-Type": "application/json"
    }
    
    print("Testing REST API v2...")
    r = requests.get(url, headers=headers)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text}")

test_rest()
