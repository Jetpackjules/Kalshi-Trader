import requests
import datetime
import time

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
SERIES_TICKER = "KXHIGHNY"
# Use a known active ticker or yesterday's closed one
TICKER = "KXHIGHNY-25NOV20-T52" 

def diagnose_recent():
    print(f"Diagnosing recent history for {TICKER}...")
    
    # Start from now and go back 7 days, day by day
    now = int(time.time())
    seconds_per_day = 86400
    
    for i in range(7):
        end_ts = now - (i * seconds_per_day)
        start_ts = end_ts - seconds_per_day
        
        date_str = datetime.datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d')
        print(f"\nChecking {date_str} (TS: {start_ts} to {end_ts})")
        
        url = f"{BASE_URL}/series/{SERIES_TICKER}/markets/{TICKER}/candlesticks"
        
        # Try with hourly candles (period_interval=60)
        params = {
            "period_interval": 60,
            "start_ts": int(start_ts),
            "end_ts": int(end_ts)
        }
        
        try:
            res = requests.get(url, params=params, timeout=5)
            if res.status_code == 200:
                data = res.json()
                candles = data.get("candlesticks", [])
                count = len(candles)
                print(f"  Status: 200 OK | Candles Found: {count}")
                if count > 0:
                    first = candles[0]
                    last = candles[-1]
                    print(f"  Data Range: {first.get('end_period_ts')} -> {last.get('end_period_ts')}")
            else:
                print(f"  Status: {res.status_code} | Msg: {res.text}")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    diagnose_recent()
