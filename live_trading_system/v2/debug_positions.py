import requests
import time
import base64
import json
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = "kalshi_prod_private_key.pem"
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

def debug_positions():
    with open(PRIVATE_KEY_PATH, 'rb') as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    # Check Balance Endpoint
    path = "/trade-api/v2/portfolio/balance"
    headers = create_headers(private_key, "GET", path)
    print(f"Fetching {API_URL}{path}...")
    resp = requests.get(f"{API_URL}{path}", headers=headers)
    print(f"Status: {resp.status_code}")
    print("Balance Response:")
    print(json.dumps(resp.json(), indent=2))

    # Check Positions Endpoint
    path = "/trade-api/v2/portfolio/positions"
    headers = create_headers(private_key, "GET", path)
    
    print(f"Fetching {API_URL}{path}...")
    resp = requests.get(f"{API_URL}{path}", headers=headers)
    
    print(f"Status: {resp.status_code}")
    print("Positions Response:")
    print(json.dumps(resp.json(), indent=2))

if __name__ == "__main__":
    debug_positions()
