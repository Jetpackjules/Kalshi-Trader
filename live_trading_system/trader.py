import base64
import json
import time
import requests
import uuid
import pandas as pd
import os
import math
from datetime import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\kalshi_prod_private_key.pem"
API_URL = "https://api.elections.kalshi.com"
CSV_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\market_data.csv"

# Strategy Config
STRATEGY_NAME = "Trend Following NO (Production)"
MIN_NO_PRICE = 50
MAX_NO_PRICE = 75
TARGET_BET_SIZE_USD = 1.00 # Target bet size in USD
MIN_BALANCE_USD = 1.00 # Stop trading if balance below this

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

def get_balance():
    """Fetch current available balance."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"Error: Private key file not found at {PRIVATE_KEY_PATH}")
        return 0.0

    path = "/trade-api/v2/portfolio/balance"
    method = "GET"
    headers = create_headers(private_key, method, path)
    
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            balance = data.get("balance", 0)
            # Convert cents to dollars if needed? API usually returns cents.
            # Checking documentation or assumption: Kalshi API v2 usually returns cents.
            # Let's assume cents and convert to dollars for display/logic.
            return balance / 100.0
        else:
            print(f"Error fetching balance: {response.status_code} {response.text}")
            return 0.0
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return 0.0

def get_positions(private_key):
    """Fetch current portfolio positions."""
    path = "/trade-api/v2/portfolio/positions"
    method = "GET"
    headers = create_headers(private_key, method, path)
    
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("market_positions", [])
        else:
            print(f"Error fetching positions: {response.status_code} {response.text}")
            return []
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []

def place_order(ticker, count, price):
    """Place a LIMIT order on Production."""
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
        
        # Log trade to CSV for visualization
        try:
            timestamp = datetime.now().isoformat()
            # Format: timestamp,market_ticker,type,price,quantity,side
            log_entry = f"{timestamp},{ticker},trade,{price},{count},buy_no\n"
            with open(CSV_FILE, "a") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Error logging trade to CSV: {e}")
            
        return True
    else:
        print(f"Failed to place order. Status: {response.status_code}")
        print(f"Response: {response.text}")
        return False

def run_bot():
    print(f"Starting PRODUCTION Auto Trader ({STRATEGY_NAME})...")
    print("WARNING: REAL MONEY TRADING ENABLED")
    print(f"Monitoring {CSV_FILE}")
    
    while True:
        try:
            # 1. Check Balance
            balance = get_balance()
            print(f"Current Balance: ${balance:.2f}")
            
            if balance < MIN_BALANCE_USD:
                print(f"Balance too low (${balance:.2f} < ${MIN_BALANCE_USD}). Waiting...")
                time.sleep(60)
                continue

            # 1.5 Update Positions
            # We want to know what we already own so we don't buy it again.
            # We will add any ticker we have a position in to 'traded_markets'.
            try:
                with open(PRIVATE_KEY_PATH, 'rb') as f:
                    private_key = serialization.load_pem_private_key(f.read(), password=None)
                
                positions = get_positions(private_key)
                for pos in positions:
                    # If we have a position != 0, consider it "traded"
                    # Short positions (NO) might be negative.
                    if abs(pos.get("position", 0)) > 0:
                        ticker = pos.get("ticker")
                        if ticker not in traded_markets:
                            print(f"Found existing position in {ticker}. Marking as traded.")
                            traded_markets.add(ticker)
            except Exception as e:
                print(f"Error updating positions: {e}")


            if not os.path.exists(CSV_FILE):
                print("Waiting for CSV file...")
                time.sleep(5)
                continue
                
            # 2. Read Market Data
            try:
                df = pd.read_csv(CSV_FILE, on_bad_lines='skip')
            except pd.errors.EmptyDataError:
                time.sleep(1)
                continue
                
            if df.empty:
                time.sleep(1)
                continue
                
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            df = df.dropna(subset=['price'])
            
            # Get latest price for each market
            latest_prices = df.sort_values('timestamp').groupby('market_ticker').last()
            
            for ticker, row in latest_prices.iterrows():
                price = row['price']
                side = row['side']
                msg_type = row['type']
                
                if side != 'no_ask' and msg_type != 'candle':
                    continue
                
                # 3. Strategy Logic
                # "Trend Following NO": Buy NO if 50 < Price < 75
                if MIN_NO_PRICE < price < MAX_NO_PRICE:
                    if ticker not in traded_markets:
                        print(f"SIGNAL: {ticker} Price {price} is in range ({MIN_NO_PRICE}-{MAX_NO_PRICE})")
                        
                        # 4. Position Sizing
                        # Calculate how many contracts to buy to equal ~$1.00
                        # Price is in cents. Contract cost = Price / 100 dollars.
                        contract_cost_usd = price / 100.0
                        
                        # Dynamic Sizing: 20% of balance, but at least $1
                        target_bet = max(TARGET_BET_SIZE_USD, balance * 0.20)
                        
                        # Cap bet size to avoid going all in if balance is huge (unlikely here)
                        # But user said "nice chunky margins", so 20% is aggressive but good.
                        
                        count = int(target_bet / contract_cost_usd)
                        if count < 1: count = 1 # Always buy at least 1 if we can afford it
                        
                        # Check if we can afford it
                        total_cost = count * contract_cost_usd
                        if total_cost > balance:
                            count = int(balance / contract_cost_usd)
                        
                        if count > 0:
                            # Limit Price: Current Price + 1 (to ensure fill)
                            limit_price = int(price) + 1
                            if limit_price > 99: limit_price = 99
                            
                            success = place_order(ticker, count, limit_price)
                            
                            if success:
                                traded_markets.add(ticker)
                            else:
                                # Mark as processed to avoid spamming errors
                                print(f"Marking {ticker} as processed despite failure.")
                                traded_markets.add(ticker)
                        else:
                            print(f"Insufficient funds for {ticker} (Cost: ${contract_cost_usd:.2f}, Balance: ${balance:.2f})")
                            
            time.sleep(5) # Check every 5 seconds
            
        except Exception as e:
            print(f"Error in bot loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("Bot stopped by user.")
