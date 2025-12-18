import requests
import datetime
import base64
import json
import time
import os
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
import csv

# --- Configuration ---
# --- Configuration ---
BASE_URL = "https://api.elections.kalshi.com"
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\kalshi_prod_private_key.pem"
OUTPUT_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\kalshi_arbitrage_scanner\arbitrage_opportunities.csv"

# --- Authentication ---
def load_private_key(path):
    with open(path, "rb") as key_file:
        return serialization.load_pem_private_key(
            key_file.read(),
            password=None
        )

def sign_request(private_key, method, path, timestamp):
    # Kalshi expects the path to start with /trade-api/v2
    msg = f"{timestamp}{method}{path}".encode('utf-8')
    signature = private_key.sign(
        msg,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def get_headers(method, path):
    timestamp = str(int(time.time() * 1000))
    private_key = load_private_key(PRIVATE_KEY_PATH)
    signature = sign_request(private_key, method, path, timestamp)
    return {
        "KALSHI-API-KEY": KEY_ID,
        "KALSHI-API-SIGNATURE": signature,
        "KALSHI-API-TIMESTAMP": timestamp,
        "Content-Type": "application/json"
    }

# --- Scanner Logic ---
def scan_markets():
    print("Fetching all active markets...")
    path = "/trade-api/v2/markets"
    url = f"{BASE_URL}{path}"
    params = {} # {"status": "active", "limit": 100} # Reduced limit just in case
    
    # Pagination loop
    all_markets = []
    cursor = None
    
    while True:
        current_params = params.copy()
        if cursor:
            current_params['cursor'] = cursor
            
        # For GET requests with params, the signature path usually doesn't include the query string in Kalshi v2?
        # Actually, let's just sign the base path. If it fails, we'll debug.
        # Documentation says: "The path of the request (e.g., /trade-api/v2/markets)"
        # It usually excludes query params.
        
        headers = get_headers("GET", path)
        try:
            response = requests.get(url, headers=headers, params=current_params)
            if response.status_code != 200:
                print(f"Error fetching markets: {response.status_code} {response.text}")
                break
                
            data = response.json()
            
            markets = data.get('markets', [])
            all_markets.extend(markets)
            
            cursor = data.get('cursor')
            if not cursor:
                break
                
            print(f"Fetched {len(all_markets)} markets so far...")
            time.sleep(0.1) # Be nice to the API
            
        except Exception as e:
            print(f"Error fetching markets: {e}")
            break

    print(f"Total markets found: {len(all_markets)}")
    
    # Initialize CSV
    file_exists = os.path.isfile(OUTPUT_FILE)
    with open(OUTPUT_FILE, 'a', newline='') as csvfile:
        fieldnames = ['timestamp', 'ticker', 'title', 'yes_ask', 'no_ask', 'total_cost', 'profit_margin', 'roi', 'type']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        # 1. Simple Arbitrage (Yes + No < 100)
        print("\n--- Scanning for Simple Arbitrage (Yes Ask + No Ask < 100) ---\n")
        
        markets_by_event = {}
        
        for market in all_markets:
            ticker = market.get('ticker')
            event_ticker = market.get('event_ticker')
            yes_ask = market.get('yes_ask')
            no_ask = market.get('no_ask')
            
            # Group for later
            if event_ticker:
                if event_ticker not in markets_by_event:
                    markets_by_event[event_ticker] = []
                markets_by_event[event_ticker].append(market)
            
            # Skip if prices are missing
            if yes_ask is None or no_ask is None:
                continue
                
            total_cost = yes_ask + no_ask
            
            if total_cost < 100:
                # HIT!
                margin = 100 - total_cost
                roi = (margin / total_cost) * 100
                timestamp = datetime.datetime.now().isoformat()
                
                print(f"💰 SIMPLE HIT! {ticker} | Cost: {total_cost}c ({yes_ask} + {no_ask}) | Profit: {margin}c | ROI: {roi:.1f}%")
                print(f"   Title: {market.get('title')}")
                
                writer.writerow({
                    'timestamp': timestamp,
                    'ticker': ticker,
                    'title': market.get('title'),
                    'yes_ask': yes_ask,
                    'no_ask': no_ask,
                    'total_cost': total_cost,
                    'profit_margin': margin,
                    'roi': f"{roi:.2f}%",
                    'type': 'Simple'
                })
                csvfile.flush()
                
        # 2. Group Arbitrage (Mutually Exclusive No + No < 100)
        print("\n--- Scanning for Group Arbitrage (No_A + No_B < 100 in same Event) ---\n")
        print("⚠️  WARNING: Verify markets are Mutually Exclusive (Only one can be YES) before trading! ⚠️\n")
        
        for event, markets in markets_by_event.items():
            if len(markets) < 2:
                continue
                
            # Check every pair
            for i in range(len(markets)):
                for j in range(i + 1, len(markets)):
                    m1 = markets[i]
                    m2 = markets[j]
                    
                    no1 = m1.get('no_ask')
                    no2 = m2.get('no_ask')
                    
                    if no1 is None or no2 is None:
                        continue
                        
                    total_cost = no1 + no2
                    
                    if total_cost < 100:
                        # HIT!
                        margin = 100 - total_cost
                        roi = (margin / total_cost) * 100
                        timestamp = datetime.datetime.now().isoformat()
                        
                        print(f"💰 GROUP HIT! {event} | {m1.get('ticker')} ({no1}c) + {m2.get('ticker')} ({no2}c) | Cost: {total_cost}c | Profit: {margin}c")
                        print(f"   M1: {m1.get('title')}")
                        print(f"   M2: {m2.get('title')}")
                        
                        writer.writerow({
                            'timestamp': timestamp,
                            'ticker': f"{m1.get('ticker')} + {m2.get('ticker')}",
                            'title': f"{m1.get('title')} + {m2.get('title')}",
                            'yes_ask': 'N/A',
                            'no_ask': f"{no1} + {no2}",
                            'total_cost': total_cost,
                            'profit_margin': margin,
                            'roi': f"{roi:.2f}%",
                            'type': 'Group (Verify Mutual Exclusivity)'
                        })
                        csvfile.flush()

if __name__ == "__main__":
    scan_markets()
