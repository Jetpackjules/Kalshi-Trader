import requests
import json
from datetime import datetime, timedelta, timezone

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

def test_date_filter():
    # Target: Nov 20, 2025
    # Open: Nov 19 10am ET -> Nov 20 11:59pm ET
    # Let's try to find markets closing on Nov 20.
    
    # Construct timestamps for Nov 20, 2025 (UTC)
    # Close time is approx Nov 21 05:00 UTC.
    
    # Let's try a wide window around the expected close time.
    # Min Close: Nov 21 00:00 UTC
    # Max Close: Nov 21 12:00 UTC
    
    min_ts = int(datetime(2025, 11, 21, 0, 0, tzinfo=timezone.utc).timestamp())
    max_ts = int(datetime(2025, 11, 21, 12, 0, tzinfo=timezone.utc).timestamp())
    
    print(f"Testing filter: min_close_ts={min_ts}, max_close_ts={max_ts}")
    
    params = {
        "series_ticker": "KXHIGHNY",
        "min_close_ts": min_ts,
        "max_close_ts": max_ts,
        "limit": 100
    }
    
    url = f"{BASE_URL}/markets"
    try:
        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")
        data = response.json()
        markets = data.get("markets", [])
        print(f"Found {len(markets)} markets")
        for m in markets[:3]:
            print(f" - {m['ticker']} (Close: {m.get('close_time')})")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_date_filter()
