import asyncio
import base64
import json
import time
import websockets
import requests
import csv
import os
from datetime import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration
KEY_ID = "cba1a3ef-189f-49ad-89ce-3443d1374833"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\kalshi_demo_test\kalshi_demo_private_key.pem"
WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"
API_URL = "https://demo-api.kalshi.co/trade-api/v2"
LOG_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\kalshi_demo_test\highny_market_data.csv"

def get_highny_ticker():
    """Fetch an active KXHIGHNY market ticker from the demo API."""
    try:
        print("Fetching active KXHIGHNY markets from Demo API...")
        # Search for markets with 'HIGHNY' in the ticker
        response = requests.get(f"{API_URL}/markets", params={"limit": 100, "status": "open"})
        if response.status_code == 200:
            data = response.json()
            markets = data.get("markets", [])
            for market in markets:
                if "HIGHNY" in market['ticker']:
                    print(f"Found active NY Temp market: {market['ticker']}")
                    return market['ticker']
            
            # If no specific HIGHNY found, return the first one as fallback for testing
            if markets:
                print(f"No HIGHNY market found. Using fallback: {markets[0]['ticker']}")
                return markets[0]['ticker']
                
        print(f"Warning: Could not fetch markets. Status: {response.status_code}")
    except Exception as e:
        print(f"Error fetching markets: {e}")
    
    return None

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

def init_csv():
    """Initialize CSV file with headers if it doesn't exist."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "market_ticker", "type", "price", "quantity", "side"])
        print(f"Created log file: {LOG_FILE}")

def log_to_csv(data):
    """Log market data to CSV."""
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        timestamp = datetime.now().isoformat()
        
        msg_type = data.get("type")
        if msg_type == "orderbook_delta":
            msg = data.get("msg", {})
            market_ticker = msg.get("market_ticker")
            
            # Log Yes Bids
            for price, qty in msg.get("yes_bid", []):
                writer.writerow([timestamp, market_ticker, "orderbook_delta", price, qty, "yes_bid"])
            # Log Yes Asks
            for price, qty in msg.get("yes_ask", []):
                writer.writerow([timestamp, market_ticker, "orderbook_delta", price, qty, "yes_ask"])
            # Log No Bids
            for price, qty in msg.get("no_bid", []):
                writer.writerow([timestamp, market_ticker, "orderbook_delta", price, qty, "no_bid"])
            # Log No Asks
            for price, qty in msg.get("no_ask", []):
                writer.writerow([timestamp, market_ticker, "orderbook_delta", price, qty, "no_ask"])
                
        elif msg_type == "orderbook_snapshot":
             msg = data.get("msg", {})
             market_ticker = msg.get("market_ticker")
             # Snapshot structure might be slightly different, usually contains full book
             # For simplicity, we'll log it similarly if structure matches, or just note it
             writer.writerow([timestamp, market_ticker, "snapshot", "N/A", "N/A", "N/A"])

async def orderbook_websocket():
    """Connect to WebSocket and log data"""
    market_ticker = get_highny_ticker()
    if not market_ticker:
        print("No active market found to subscribe to.")
        return

    init_csv()
    
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"Error: Private key file not found at {PRIVATE_KEY_PATH}")
        return

    ws_headers = create_headers(private_key, "GET", "/trade-api/ws/v2")
    
    print(f"Connecting to {WS_URL} for {market_ticker}...")
    async with websockets.connect(WS_URL, additional_headers=ws_headers) as websocket:
        print(f"Connected! Logging data to {LOG_FILE}")
        
        subscribe_msg = {
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_ticker": market_ticker
            }
        }
        await websocket.send(json.dumps(subscribe_msg))
        
        async for message in websocket:
            data = json.loads(message)
            # print(f"Received: {data['type']}") # Debug print
            log_to_csv(data)

if __name__ == "__main__":
    try:
        asyncio.run(orderbook_websocket())
    except KeyboardInterrupt:
        print("Logging stopped by user.")
