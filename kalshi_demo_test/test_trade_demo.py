import base64
import json
import time
import requests
import uuid
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration
KEY_ID = "cba1a3ef-189f-49ad-89ce-3443d1374833"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\kalshi_demo_test\kalshi_demo_private_key.pem"
API_URL = "https://demo-api.kalshi.co"

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

def get_active_ticker():
    """Fetch an active market ticker from the demo API."""
    try:
        print("Fetching active markets from Demo API...")
        # Public endpoint, no auth needed
        response = requests.get(f"{API_URL}/trade-api/v2/markets", params={"limit": 5, "status": "open"})
        if response.status_code == 200:
            data = response.json()
            markets = data.get("markets", [])
            if markets:
                ticker = markets[0]['ticker']
                print(f"Found active market: {ticker}")
                return ticker
        print(f"Warning: Could not fetch markets. Status: {response.status_code}")
    except Exception as e:
        print(f"Error fetching markets: {e}")
    return None

def place_order(ticker):
    """Place a test order."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"Error: Private key file not found at {PRIVATE_KEY_PATH}")
        return

    # 1. Get Market Details to know valid sides/prices
    # For simplicity, we'll place a MARKET order to buy NO (or YES)
    
    path = "/trade-api/v2/portfolio/orders"
    method = "POST"
    
    # Buy 1 contract of NO
    # Note: On Demo, liquidity might be low, so a market order might not fill immediately 
    # or might fill at a weird price. But we just want to test the API call.
    order_id = str(uuid.uuid4())
    payload = {
        "action": "buy",
        "count": 1,
        "side": "no", # Buying NO
        "ticker": ticker,
        "type": "limit",
        "no_price": 99, # Limit price: Buy NO at max 99 cents
        "client_order_id": order_id
    }
    
    headers = create_headers(private_key, method, path)
    
    print(f"Placing BUY NO order for {ticker}...")
    response = requests.post(f"{API_URL}{path}", headers=headers, json=payload)
    
    if response.status_code == 201:
        data = response.json()
        order = data.get("order", {})
        print(f"SUCCESS! Order placed.")
        print(f"Order ID: {order.get('order_id')}")
        print(f"Status: {order.get('status')}")
    else:
        print(f"Failed to place order. Status: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    ticker = get_active_ticker()
    if ticker:
        place_order(ticker)
    else:
        print("Could not find an active market to test with.")
