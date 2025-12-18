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
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\price_checker\kalshi_prod_private_key.pem"
API_URL = "https://api.elections.kalshi.com/trade-api/v2"

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

def get_todays_highny_tickers():
    """Fetch ALL active KXHIGHNY market tickers for TODAY from the Production API."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"Error: Private key file not found at {PRIVATE_KEY_PATH}")
        return []

    tickers = []
    try:
        # Search specifically for the KXHIGHNY series
        response = requests.get(f"{API_URL}/markets", params={"series_ticker": "KXHIGHNY", "status": "open"})
        if response.status_code == 200:
            data = response.json()
            markets = data.get("markets", [])
            
            if markets:
                # Get today's date string in Kalshi format (e.g., 25NOV25)
                today_str = datetime.now().strftime("%y%b%d").upper()
                
                for market in markets:
                    if today_str in market['ticker']:
                        tickers.append(market['ticker'])
    except Exception as e:
        print(f"Error fetching markets: {e}")
    
    return tickers

def get_market_price(ticker):
    """Fetch current orderbook for a ticker."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
            
        path = f"/markets/{ticker}/orderbook"
        method = "GET"
        headers = create_headers(private_key, method, path)
        
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            orderbook = data.get("orderbook", {})
            
            # We want "NO" Price.
            # "Buy NO" price is the 'no_ask' (lowest price someone is selling NO for).
            # "Sell NO" price is the 'no_bid' (highest price someone is buying NO for).
            
            no_asks = orderbook.get("no", []) # List of [price, qty]
            yes_bids = orderbook.get("yes", [])
            
            # Kalshi orderbook structure:
            # "yes": [[price, qty], ...] (Bids for YES)
            # "no": [[price, qty], ...] (Bids for NO? Or Asks? API v2 usually gives bids/asks separately)
            
            # Actually, let's look at the /markets/{ticker} endpoint for simple "last price" or "yes_bid/yes_ask"
            # But orderbook is more accurate for "current instant".
            
            # Let's use the 'markets' endpoint again for the specific ticker to get the summary
            path_summary = f"/markets/{ticker}"
            headers_summary = create_headers(private_key, "GET", path_summary)
            resp_summary = requests.get(f"{API_URL}{path_summary}", headers=headers_summary)
            if resp_summary.status_code == 200:
                m_data = resp_summary.json().get("market", {})
                
                yes_bid = m_data.get("yes_bid")
                yes_ask = m_data.get("yes_ask")
                no_bid = m_data.get("no_bid")
                no_ask = m_data.get("no_ask")
                last_price = m_data.get("last_price")
                
                return {
                    "ticker": ticker,
                    "no_ask": no_ask, # Cost to Buy NO
                    "no_bid": no_bid, # Sell NO
                    "last_price": last_price
                }
                
    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
    return None

def main():
    print("--- Kalshi NY Max Temp Price Checker ---")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tickers = get_todays_highny_tickers()
    if not tickers:
        print("No active markets found for today.")
        return

    print(f"Found {len(tickers)} markets.")
    print("-" * 60)
    print(f"{'Ticker':<30} | {'Buy NO ($)':<12} | {'Sell NO ($)':<12} | {'Last Traded':<12}")
    print("-" * 60)
    
    for ticker in tickers:
        data = get_market_price(ticker)
        if data:
            no_ask = f"{data['no_ask']}¢" if data['no_ask'] else "N/A"
            no_bid = f"{data['no_bid']}¢" if data['no_bid'] else "N/A"
            last = f"{data['last_price']}¢" if data['last_price'] else "N/A"
            
            # Shorten ticker for display
            display_ticker = ticker.replace("KXHIGHNY-", "")
            
            print(f"{display_ticker:<30} | {no_ask:<12} | {no_bid:<12} | {last:<12}")
            
    print("-" * 60)

if __name__ == "__main__":
    main()
