import base64
import json
import time
import requests
import uuid
from datetime import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\kalshi_prod_private_key.pem"
API_URL = "https://api.elections.kalshi.com"

def sign_pss_text(private_key, text: str) -> str:
    message = text.encode('utf-8')
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def create_headers(private_key, method: str, path: str) -> dict:
    timestamp = str(int(time.time() * 1000))
    msg_string = timestamp + method + path.split('?')[0]
    signature = sign_pss_text(private_key, msg_string)
    return {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }

def test_endpoint(path):
    print(f"Testing endpoint: {path}")
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        
        headers = create_headers(private_key, "GET", path)
        response = requests.get(f"{API_URL}{path}", headers=headers)
        
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            # Print first 2 items if list, or keys if dict
            data = response.json()
            if isinstance(data, list):
                print(json.dumps(data[:2], indent=2))
            elif isinstance(data, dict):
                # Print keys
                print(f"Keys: {list(data.keys())}")
                # Print first item of any list value
                for k, v in data.items():
                    if isinstance(v, list) and v:
                        print(f"Sample {k}: {json.dumps(v[0], indent=2)}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        return False

if __name__ == "__main__":
    # Variations
    test_endpoint("/trade-api/v2/portfolio/settlements") # Retrying just in case
    test_endpoint("/trade-api/v2/portfolio/settlement")
    test_endpoint("/trade-api/v2/portfolio/history")
    test_endpoint("/trade-api/v2/markets/trades") # Maybe market trades?
