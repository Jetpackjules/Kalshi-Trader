import requests
import json
from datetime import datetime

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

def inspect_market():
    # Fetch all markets for NOV20
    print("Fetching markets for NOV20...")
    
    # We can use the public markets endpoint with a filter?
    # Or just fetch all and filter by ticker date.
    url = f"{BASE_URL}/markets"
    params = {"series_ticker": "KXHIGHNY", "limit": 100, "status": "settled"} 
    # Note: settled markets for NOV20
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Failed to fetch markets: {response.text}")
        return
        
    markets = response.json().get('markets', [])
    print(f"Found {len(markets)} markets.")
    
    for m in markets:
        ticker = m['ticker']
        if "NOV20" in ticker:
            print(f"Ticker: {ticker}")
            print(f"  Title: {m['title']}")
            print(f"  Subtitle: {m['subtitle']}")
            print(f"  Strike Type: {m.get('strike_type')}")
            print(f"  Floor/Cap: {m.get('floor_strike')} - {m.get('cap_strike')}")
            print("-" * 20)

if __name__ == "__main__":
    inspect_market()
