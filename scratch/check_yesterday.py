import requests
import datetime

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

def check_yesterday():
    # 1. Try to find yesterday's markets
    # Yesterday was Nov 20, 2025 based on current date Nov 21
    target_date_str = "25NOV20"
    series_ticker = "KXHIGHNY"
    
    print(f"Searching for markets with date string: {target_date_str}")
    
    # Try fetching all markets for the series, maybe status=all or closed works?
    # The API documentation isn't fully known, but we can guess status params
    statuses = ["open", "closed", "settled", "all"]
    found_ticker = None
    
    for status in statuses:
        print(f"\nChecking status='{status}'...")
        url = f"{BASE_URL}/markets?series_ticker={series_ticker}&status={status}&limit=200"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                markets = data.get("markets", [])
                print(f"Found {len(markets)} markets")
                
                for m in markets:
                    if target_date_str in m["ticker"]:
                        print(f"  FOUND TARGET: {m['ticker']} (Status: {m.get('status')})")
                        found_ticker = m["ticker"]
                        break
            else:
                print(f"  Failed with status {response.status_code}")
        except Exception as e:
            print(f"  Error: {e}")
            
        if found_ticker:
            break
            
    if not found_ticker:
        # Fallback: construct a ticker manually and see if we can hit it
        # Example: KXHIGHNY-25NOV20-T50
        found_ticker = f"{series_ticker}-{target_date_str}-T50"
        print(f"\nNo market found in lists. Trying manual ticker: {found_ticker}")

    # 2. Try to get details/history for the found ticker
    if found_ticker:
        print(f"\n--- Probing data for {found_ticker} ---")
        
        # A. Orderbook
        print("1. Checking Orderbook...")
        url = f"{BASE_URL}/markets/{found_ticker}/orderbook"
        try:
            res = requests.get(url)
            print(f"   Status: {res.status_code}")
            if res.status_code == 200:
                data = res.json()
                ob = data.get("orderbook", {})
                yes_len = len(ob.get("yes") or [])
                no_len = len(ob.get("no") or [])
                print(f"   Data: YES orders={yes_len}, NO orders={no_len}")
        except Exception as e:
            print(f"   Error: {e}")

        # B. Candlesticks (History)
        # Try standard timestamps for yesterday
        # Nov 20 00:00 UTC to Nov 21 00:00 UTC
        start_ts = 1732060800 # Nov 20 00:00 UTC (approx)
        end_ts = 1732147200   # Nov 21 00:00 UTC (approx)
        
        print("2. Checking Candlesticks (History)...")
        # Try a few endpoint variations
        endpoints = [
            f"/markets/{found_ticker}/candles?interval=1h&start_time={start_ts}&end_time={end_ts}",
            f"/series/{series_ticker}/markets/{found_ticker}/candles?interval=1h",
            f"/markets/{found_ticker}/history?interval=1h"
        ]
        
        for ep in endpoints:
            url = f"{BASE_URL}{ep}"
            print(f"   Trying: {ep}")
            try:
                res = requests.get(url)
                print(f"   Status: {res.status_code}")
                if res.status_code == 200:
                    print(f"   Response: {res.text[:200]}...")
            except Exception as e:
                print(f"   Error: {e}")

        # C. Trades
        print("3. Checking Trades...")
        url = f"{BASE_URL}/markets/{found_ticker}/trades?limit=10"
        try:
            res = requests.get(url)
            print(f"   Status: {res.status_code}")
            if res.status_code == 200:
                print(f"   Response: {res.text[:200]}...")
        except Exception as e:
            print(f"   Error: {e}")

if __name__ == "__main__":
    check_yesterday()
