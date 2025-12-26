import requests
import time
import base64
import json
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Config
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

def main():
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except Exception as e:
        print(f"Failed to load key: {e}")
        return

    # 1. Balance
    path = "/trade-api/v2/portfolio/balance"
    headers = create_headers(private_key, "GET", path)
    resp = requests.get(f"{API_URL}{path}", headers=headers)
    print("\n=== BALANCE ===")
    if resp.status_code == 200:
        print(json.dumps(resp.json(), indent=2))
    else:
        print(f"Error: {resp.status_code} {resp.text}")

    # 2. Orders (Open)
    path = "/trade-api/v2/portfolio/orders"
    headers = create_headers(private_key, "GET", path)
    resp = requests.get(f"{API_URL}{path}", headers=headers)
    print("\n=== ORDERS (First 2) ===")
    if resp.status_code == 200:
        orders = resp.json().get("orders", [])
        if orders:
            print(json.dumps(orders[:2], indent=2))
        else:
            print("No open orders found.")
    else:
        print(f"Error: {resp.status_code} {resp.text}")

    # 3. Positions
    path = "/trade-api/v2/portfolio/positions"
    headers = create_headers(private_key, "GET", path)
    resp = requests.get(f"{API_URL}{path}", headers=headers)
    print("\n=== POSITIONS (First 2) ===")
    if resp.status_code == 200:
        positions = resp.json().get("market_positions", [])
        if positions:
            print(json.dumps(positions[:2], indent=2))
        else:
            print("No positions found.")
    else:
        print(f"Error: {resp.status_code} {resp.text}")

if __name__ == "__main__":
    main()
