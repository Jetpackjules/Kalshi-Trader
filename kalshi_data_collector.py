import requests
import pandas as pd
from datetime import datetime, timezone
import time
import os
import logging
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("kalshi_collector.log"),
        logging.StreamHandler()
    ]
)

DATA_FILE = "kalshi_market_history.csv"
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

def fetch_market_snapshot():
    """Fetches current snapshot of NYC High Temp markets using public API."""
    try:
        # Fetch active markets for NYC High Temp
        url = f"{BASE_URL}/markets"
        params = {
            "series_ticker": "KXHIGHNY",
            "status": "open",
            "limit": 100
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        markets = data.get("markets", [])
        
        if not markets:
            logging.info("No active markets found.")
            return []
            
        snapshot_data = []
        timestamp = datetime.now(timezone.utc).isoformat()
        
        for market in markets:
            ticker = market.get("ticker")
            
            # For public API, we might not get full orderbook in the list response.
            # But 'yes_bid', 'yes_ask' are usually top level fields in the market object.
            # Let's check what we get.
            
            snapshot_data.append({
                "timestamp": timestamp,
                "ticker": ticker,
                "yes_bid": market.get("yes_bid"),
                "yes_ask": market.get("yes_ask"),
                "no_bid": market.get("no_bid"),
                "no_ask": market.get("no_ask"),
                "last_price": market.get("last_price"),
                "open_interest": market.get("open_interest"),
                "volume": market.get("volume"),
                "liquidity": market.get("liquidity")
            })
            
        return snapshot_data
        
    except Exception as e:
        logging.error(f"Error fetching market snapshot: {e}")
        return []

def save_data(data):
    """Appends new data to CSV."""
    if not data:
        return

    df_new = pd.DataFrame(data)
    
    if os.path.exists(DATA_FILE):
        df_new.to_csv(DATA_FILE, mode='a', header=False, index=False)
    else:
        df_new.to_csv(DATA_FILE, index=False)
    
    logging.info(f"Saved {len(data)} market records.")

def main():
    logging.info("Starting Kalshi Data Collector (Requests)...")
    
    while True:
        data = fetch_market_snapshot()
        save_data(data)
        
        # Poll every minute
        time.sleep(60)

if __name__ == "__main__":
    main()
