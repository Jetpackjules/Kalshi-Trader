import asyncio
import base64
import json
import time
import websockets
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration
KEY_ID = "cba1a3ef-189f-49ad-89ce-3443d1374833"
# Using absolute path to the key file found in scratch directory
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\kalshi_demo_test\kalshi_demo_private_key.pem"
WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"
API_URL = "https://demo-api.kalshi.co/trade-api/v2"

def get_active_ticker():
    """Fetch an active market ticker from the demo API to ensure we subscribe to something valid."""
    try:
        # Try to find a weather market or any open market
        print("Fetching active markets from Demo API...")
        response = requests.get(f"{API_URL}/markets", params={"limit": 5, "status": "open"})
        if response.status_code == 200:
            data = response.json()
            markets = data.get("markets", [])
            if markets:
                ticker = markets[0]['ticker']
                print(f"Found active market: {ticker}")
                return ticker
        print(f"Warning: Could not fetch markets. Status: {response.status_code}, Body: {response.text}")
    except Exception as e:
        print(f"Error fetching markets: {e}")
    
    # Fallback to a hardcoded guess if fetch fails, though it might not work
    return "KXHIGHNY-25NOV25-T50" 

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

async def orderbook_websocket():
    """Connect to WebSocket and subscribe to orderbook"""
    market_ticker = get_active_ticker()
    
    try:
        # Load private key
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=None
            )
    except FileNotFoundError:
        print(f"Error: Private key file not found at {PRIVATE_KEY_PATH}")
        return

    # Create WebSocket headers
    ws_headers = create_headers(private_key, "GET", "/trade-api/ws/v2")
    
    print(f"Connecting to {WS_URL}...")
    try:
        async with websockets.connect(WS_URL, additional_headers=ws_headers) as websocket:
            print(f"Connected! Subscribing to orderbook for {market_ticker}")
            
            # Subscribe to orderbook
            subscribe_msg = {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta"],
                    "market_ticker": market_ticker
                }
            }
            await websocket.send(json.dumps(subscribe_msg))
            
            # Process messages
            print("Listening for messages (Press Ctrl+C to stop)...")
            msg_count = 0
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "subscribed":
                    print(f"Subscribed: {data}")
                elif msg_type == "orderbook_snapshot":
                    print(f"Orderbook snapshot received for {data.get('market_ticker')}")
                elif msg_type == "orderbook_delta":
                    print(f"Orderbook update: {data}")
                elif msg_type == "error":
                    print(f"Error: {data}")
                else:
                    print(f"Message: {data}")
                
                msg_count += 1
                if msg_count >= 5: # Stop after a few messages for the test
                    print("Received 5 messages, test successful. Closing connection.")
                    break
                    
    except Exception as e:
        print(f"WebSocket Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(orderbook_websocket())
    except KeyboardInterrupt:
        print("Stopped by user")
