import requests
import uuid
import base64
import time
import json
import csv
import re
from datetime import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from fetch_forecast import get_nws_forecast

# --- Configuration ---
API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\kalshi_prod_private_key.pem"
OUTPUT_FILE = "value_opportunities.csv"

# --- Authentication ---
def load_private_key(path):
    with open(path, "rb") as key_file:
        return serialization.load_pem_private_key(
            key_file.read(),
            password=None
        )

def sign_message(private_key, message):
    signature = private_key.sign(
        message.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def get_auth_headers():
    timestamp = str(int(time.time() * 1000))
    msg = f"{timestamp}GET/trade-api/v2/markets"
    private_key = load_private_key(PRIVATE_KEY_PATH)
    signature = sign_message(private_key, msg)
    
    return {
        "KALSHI-API-KEY": KEY_ID,
        "KALSHI-API-SIGNATURE": signature,
        "KALSHI-API-TIMESTAMP": timestamp,
        "Content-Type": "application/json"
    }

# --- Market Data ---
def get_active_weather_markets():
    """Fetch all active KXHIGHNY markets."""
    url = f"{API_BASE}/markets"
    params = {
        "series_ticker": "KXHIGHNY",
        "status": "open",
        "limit": 200
    }
    
    # We need to sign the request with the params included in the path?
    # The signature logic usually requires the exact path+query or just path depending on implementation.
    # Kalshi docs say: timestamp + method + path (without query params usually, but let's check trader.py logic if needed).
    # Actually, for GET, it's usually just the path.
    # Let's try fetching.
    
    # Re-generating headers for this specific request if needed, but generic GET usually works with base path signature if not strict.
    # Actually, let's use the robust auth from scanner.py which signs the specific path.
    
    timestamp = str(int(time.time() * 1000))
    path = "/trade-api/v2/markets"
    # Note: If params are used, they might need to be in the signature if passed in URL.
    # Safest is to sign the base path and pass params.
    
    msg = f"{timestamp}GET{path}"
    private_key = load_private_key(PRIVATE_KEY_PATH)
    signature = sign_message(private_key, msg)
    
    headers = {
        "KALSHI-API-KEY": KEY_ID,
        "KALSHI-API-SIGNATURE": signature,
        "KALSHI-API-TIMESTAMP": timestamp,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get("markets", [])
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []

def parse_ticker_date(ticker):
    # KXHIGHNY-25DEC06-T50
    match = re.search(r'-(\d{2})([A-Z]{3})(\d{2})-', ticker)
    if match:
        year_short = match.group(1) # 25
        month_str = match.group(2) # DEC
        day_str = match.group(3) # 06
        
        year = int("20" + year_short)
        try:
            date_obj = datetime.strptime(f"{year}-{month_str}-{day_str}", "%Y-%b-%d").date()
            return date_obj
        except ValueError:
            return None
    return None

def parse_strike(ticker):
    # ...-T50 (Greater than 50) or ...-B50 (Less than 50)
    # Actually Kalshi High Temp usually uses "High Temp > X" which corresponds to floor_strike.
    # Ticker format: KXHIGHNY-25DEC06-T50
    # T = Top/Above? B = Below?
    # Let's rely on the market object's 'strike_type', 'floor_strike', 'cap_strike'.
    pass

# --- Scanner Logic ---
def scan_markets():
    print("--- Starting Weather Value Scanner ---")
    
    # 1. Get Forecasts
    print("Fetching NWS Forecast...")
    forecasts = get_nws_forecast() # Returns {date: {temp, name, ...}}
    if not forecasts:
        print("Failed to get forecast. Exiting.")
        return
        
    print(f"Got forecasts for {len(forecasts)} days.")
    
    # 2. Get Markets
    print("Fetching Active Kalshi Markets...")
    markets = get_active_weather_markets()
    print(f"Found {len(markets)} active markets.")
    
    hits = []
    
    for market in markets:
        ticker = market['ticker']
        market_date = parse_ticker_date(ticker)
        
        if not market_date:
            continue
            
        if market_date not in forecasts:
            # No forecast for this date (too far out or past)
            continue
            
        forecast = forecasts[market_date]
        forecast_temp = forecast['temp']
        
        # Analyze Market
        # We look for "Yes" price.
        yes_ask = market.get('yes_ask')
        no_ask = market.get('no_ask')
        
        strike_type = market.get('strike_type')
        floor = market.get('floor_strike')
        cap = market.get('cap_strike')
        strike = floor if strike_type == 'greater' else cap
        
        print(f"Checking {market_date}: Forecast {forecast_temp}F vs Strike {strike} ({strike_type}) | Price: Yes {yes_ask}c / No {no_ask}c")
        
        if not yes_ask and not no_ask:
            continue
        
        # Logic:
        # If Forecast says 50F.
        # Market: High > 45F (floor=45).
        # We expect YES to win.
        # If Yes Ask is low (e.g. < 80c), it's a buy.
        
        # Margin of safety
        MARGIN = 3 # degrees
        
        signal = None
        confidence = 0
        
        if strike_type == 'greater' and floor is not None:
            # Market: Temp > Floor
            if forecast_temp > (floor + MARGIN):
                # Forecast is significantly higher than floor -> YES likely
                if yes_ask and yes_ask < 80: # Arbitrary value threshold
                    signal = "BUY_YES"
                    confidence = forecast_temp - floor
            elif forecast_temp < (floor - MARGIN):
                # Forecast is significantly lower than floor -> NO likely
                if no_ask and no_ask < 80:
                    signal = "BUY_NO"
                    confidence = floor - forecast_temp
                    
        elif strike_type == 'less' and cap is not None:
            # Market: Temp < Cap
            if forecast_temp < (cap - MARGIN):
                # Forecast is significantly lower than cap -> YES likely
                if yes_ask and yes_ask < 80:
                    signal = "BUY_YES"
                    confidence = cap - forecast_temp
            elif forecast_temp > (cap + MARGIN):
                # Forecast is significantly higher than cap -> NO likely
                if no_ask and no_ask < 80:
                    signal = "BUY_NO"
                    confidence = forecast_temp - cap
                    
        if signal:
            hit = {
                'ticker': ticker,
                'date': market_date,
                'forecast': forecast_temp,
                'strike': floor if strike_type == 'greater' else cap,
                'type': strike_type,
                'signal': signal,
                'price': yes_ask if signal == "BUY_YES" else no_ask,
                'diff': confidence
            }
            hits.append(hit)
            print(f"HIT: {market_date} | Forecast {forecast_temp}F | Market {ticker} | {signal} @ {hit['price']}c | Diff: {confidence:.1f}")

    # Save to CSV
    if hits:
        keys = hits[0].keys()
        with open(OUTPUT_FILE, 'w', newline='') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(hits)
        print(f"\nSaved {len(hits)} opportunities to {OUTPUT_FILE}")
    else:
        print("\nNo value opportunities found with current margin.")

if __name__ == "__main__":
    scan_markets()
