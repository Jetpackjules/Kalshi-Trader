import base64
import json
import time
import requests
import os
from datetime import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\kalshi_prod_private_key.pem"
API_URL = "https://api.elections.kalshi.com"

def sign_pss_text(private_key, text: str) -> str:
    """Sign message using RSA-PSS"""
    message = text.encode('utf-8')
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH
        ),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def create_headers(private_key, method: str, path: str) -> dict:
    """Create authentication headers"""
    timestamp = str(int(time.time() * 1000))
    msg_string = timestamp + method + path.split('?')[0]
    signature = sign_pss_text(private_key, msg_string)
    return {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }

def get_positions():
    """Fetch current portfolio positions."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"Error: Private key file not found at {PRIVATE_KEY_PATH}")
        return

    path = "/trade-api/v2/portfolio/positions"
    method = "GET"
    headers = create_headers(private_key, method, path)
    
    print(f"Fetching positions from {API_URL}{path}...")
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            # print("RAW RESPONSE:", json.dumps(data, indent=2))
            positions = data.get("market_positions", [])
            print(f"Found {len(positions)} positions.")
            for pos in positions:
                print(f"Ticker: {pos.get('ticker')}, Side: {pos.get('side')}, Count: {pos.get('position')}, Cost: {pos.get('realized_pnl')}") # realized_pnl isn't cost, but let's just see what we get
                # Actually, let's just print the whole object for inspection
                print(json.dumps(pos, indent=2))
            return positions
        else:
            print(f"Error fetching positions: {response.status_code} {response.text}")
            return []
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []

if __name__ == "__main__":
    get_positions()
