import sys
import os
import json
import time
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
import base64

# Configuration
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
API_URL = "https://api.elections.kalshi.com"
KEY_PATH = "keys/kalshi_prod_private_key.pem"

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

def main():
    print("--- Checking Balance & Positions ---")
    
    # Load Key
    try:
        with open(KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except Exception as e:
        print(f"Error loading key: {e}")
        return

    session = requests.Session()

    # 1. Balance
    path = "/trade-api/v2/portfolio/balance"
    headers = create_headers(private_key, "GET", path)
    resp = session.get(API_URL + path, headers=headers)
    print(f"\nBalance Response ({resp.status_code}):")
    print(json.dumps(resp.json(), indent=2))

    # 2. Positions
    path = "/trade-api/v2/portfolio/positions"
    headers = create_headers(private_key, "GET", path)
    resp = session.get(API_URL + path, headers=headers)
    print(f"\nPositions Response ({resp.status_code}):")
    data = resp.json()
    active_positions = [p for p in data.get("market_positions", []) if p.get("position", 0) != 0]
    print(json.dumps(active_positions, indent=2))

if __name__ == "__main__":
    main()
