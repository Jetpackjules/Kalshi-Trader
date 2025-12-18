import requests
import json
from datetime import datetime

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
TICKER = "KXHIGHNY-25NOV20-T52"

def get_market_details(ticker):
    url = f"{BASE_URL}/markets/{ticker}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        market = data.get("market", {})
        
        print(f"--- Market Details for {ticker} ---")
        # Parse ISO format: 2025-11-21T04:59:00Z
        open_time = market.get('open_time')
        close_time = market.get('close_time')
        expiration_time = market.get('expiration_time')
        
        print(f"Raw Open: {open_time}")
        print(f"Raw Close: {close_time}")
        
        # Convert to readable if possible (assuming UTC Z)
        if close_time:
            dt = datetime.fromisoformat(close_time.replace('Z', '+00:00'))
            print(f"Close Time (UTC): {dt}")
            print(f"Close Time (ET): {dt.astimezone().strftime('%Y-%m-%d %I:%M %p %Z')}") # Local system time (likely ET or PT)


        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_market_details(TICKER)
