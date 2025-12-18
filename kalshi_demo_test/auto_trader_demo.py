import base64
import json
import time
import requests
import uuid
import pandas as pd
import os
from datetime import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration
KEY_ID = "cba1a3ef-189f-49ad-89ce-3443d1374833"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\kalshi_demo_test\kalshi_demo_private_key.pem"
API_URL = "https://demo-api.kalshi.co"
CSV_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\kalshi_demo_test\highny_market_data_prod.csv"

# Strategy Config
STRATEGY_NAME = "Trend Following NO"
MIN_NO_PRICE = 50
MAX_NO_PRICE = 75
BET_SIZE_CONTRACTS = 10 # Contracts per trade
MAX_POSITIONS_PER_MARKET = 1

# State
traded_markets = set()

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

def place_order(ticker, count, price):
    """Place a LIMIT order on Demo."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"Error: Private key file not found at {PRIVATE_KEY_PATH}")
        return False

    path = "/trade-api/v2/portfolio/orders"
    method = "POST"
    
    order_id = str(uuid.uuid4())
    payload = {
        "action": "buy",
        "count": count,
        "side": "no",
        "ticker": ticker,
        "type": "limit",
        "no_price": price, # Limit price
        "client_order_id": order_id
    }
    
    headers = create_headers(private_key, method, path)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Placing BUY NO order for {ticker} (Price: {price}, Count: {count})...")
    response = requests.post(f"{API_URL}{path}", headers=headers, json=payload)
    
    if response.status_code == 201:
        data = response.json()
        order = data.get("order", {})
        print(f"SUCCESS! Order placed. ID: {order.get('order_id')}")
        return True
    else:
        print(f"Failed to place order. Status: {response.status_code}")
        print(f"Response: {response.text}")
        return False

def run_bot():
    print(f"Starting Auto Trader ({STRATEGY_NAME})...")
    print(f"Monitoring {CSV_FILE}")
    
    last_processed_timestamp = None
    
    while True:
        try:
            if not os.path.exists(CSV_FILE):
                print("Waiting for CSV file...")
                time.sleep(5)
                continue
                
            # Read CSV
            try:
                df = pd.read_csv(CSV_FILE, on_bad_lines='skip')
            except pd.errors.EmptyDataError:
                time.sleep(1)
                continue
                
            if df.empty:
                time.sleep(1)
                continue
                
            # Filter for relevant data (NO prices)
            # We use 'no_ask' (cost to buy NO) or 'candle' data
            # Strategy: Buy NO if 50 < Price < 75
            
            # Normalize data
            # If 'side' is 'no_ask', price is the price.
            # If 'type' is 'candle' (historical trade), price is the price.
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            df = df.dropna(subset=['price'])
            
            # Get latest price for each market
            latest_prices = df.sort_values('timestamp').groupby('market_ticker').last()
            
            for ticker, row in latest_prices.iterrows():
                price = row['price']
                side = row['side']
                msg_type = row['type']
                
                # Check if this is a valid price update for us
                # We want the cost to BUY NO.
                # If side='no_ask', price is the ask price for NO.
                # If type='candle', price is the last trade price. We assume we can buy near this price.
                
                if side != 'no_ask' and msg_type != 'candle':
                    continue
                
                # Strategy Logic
                # "Trend Following NO": Buy NO if 50 < Price < 75
                if MIN_NO_PRICE < price < MAX_NO_PRICE:
                    if ticker not in traded_markets:
                        print(f"SIGNAL: {ticker} Price {price} is in range ({MIN_NO_PRICE}-{MAX_NO_PRICE})")
                        
                        # Execute Trade
                        # Use a slightly higher limit price to ensure fill? Or just the current price?
                        # Let's use current price + 1 as limit
                        limit_price = int(price) + 1
                        if limit_price > 99: limit_price = 99
                        
                        success = place_order(ticker, BET_SIZE_CONTRACTS, limit_price)
                        
                        if success:
                            traded_markets.add(ticker)
                        else:
                            # If failed (e.g. market not found on demo), mark as traded to avoid spamming
                            print(f"Marking {ticker} as processed despite failure to avoid loop.")
                            traded_markets.add(ticker)
                            
            time.sleep(5) # Check every 5 seconds
            
        except Exception as e:
            print(f"Error in bot loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("Bot stopped by user.")
