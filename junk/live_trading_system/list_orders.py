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

def get_orders():
    """Fetch current open orders."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"Error: Private key file not found at {PRIVATE_KEY_PATH}")
        return

    # Endpoint for orders
    path = "/trade-api/v2/portfolio/orders"
    # Adding query param to filter for active orders if supported, or just fetch all
    # Usually ?status=active or similar. Let's try without first to see what we get, 
    # or assume default is all recent orders.
    # Actually, let's try to filter for 'active' status if possible, but standard endpoint usually returns list.
    
    method = "GET"
    headers = create_headers(private_key, method, path)
    
    print(f"Fetching orders from {API_URL}{path}...")
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            orders = data.get("orders", [])
            print(f"Found {len(orders)} orders.")
            
            canceled_orders = [o for o in orders if o.get('status') == 'canceled']
            print(f"Found {len(canceled_orders)} CANCELED orders.")
            
            print("Most recent 10 CANCELED orders:")
            # Sort by created_time descending just in case
            canceled_orders.sort(key=lambda x: x.get('created_time'), reverse=True)
            
            for o in canceled_orders[:10]:
                print(f"Time: {o.get('created_time')}, Ticker: {o.get('ticker')}, Price: {o.get('yes_price')}/{o.get('no_price')}, ID: {o.get('order_id')}")
                    
            return orders
        else:
            print(f"Error fetching orders: {response.status_code} {response.text}")
            return []
    except Exception as e:
        print(f"Error fetching orders: {e}")
        return []

if __name__ == "__main__":
    get_orders()
