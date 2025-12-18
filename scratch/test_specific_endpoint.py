import requests
import datetime

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
SERIES_TICKER = "KXHIGHNY"

# Known tickers
# Yesterday's finalized market (from previous check)
CLOSED_TICKER = "KXHIGHNY-25NOV20-T52" 

def get_active_ticker():
    try:
        url = f"{BASE_URL}/markets?series_ticker={SERIES_TICKER}&status=open&limit=1"
        res = requests.get(url)
        if res.status_code == 200:
            markets = res.json().get("markets", [])
            if markets:
                return markets[0]["ticker"]
    except:
        pass
    return "KXHIGHNY-25NOV21-T50" # Fallback guess

def test_endpoint(ticker, label):
    print(f"\n--- Testing {label}: {ticker} ---")
    
    # Timestamps for the last 24-48 hours to ensure we cover the relevant period
    # Current time is approx Nov 21, so let's look at Nov 20-21
    start_ts = 1732060800 # Nov 20 00:00 UTC
    end_ts = 1732233600   # Nov 22 00:00 UTC
    
    # Construct URL as requested
    # https://api.elections.kalshi.com/trade-api/v2/series/{series_ticker}/markets/{ticker}/candlesticks
    url = f"{BASE_URL}/series/{SERIES_TICKER}/markets/{ticker}/candlesticks"
    
    # Try different interval formats (integers only)
    intervals = [1, 60, 1440]
    
    for interval in intervals:
        print(f"\nTesting interval: {interval}")
        # Test the max possible duration from user's start time
        # 4900 hours is safe under the 5000 limit
        user_start = 1714233599
        duration = 4900 * interval * 60 if isinstance(interval, int) else 4900 * 3600
        
        print(f"Requesting {duration/3600} hours starting from user's start_ts: {user_start}")
        
        params = {
            "period_interval": interval,
            "start_ts": user_start,
            "end_ts": user_start + duration
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                candlesticks = data.get("candlesticks", [])
                print(f"Found {len(candlesticks)} candlesticks")
                if candlesticks:
                    print("First candle sample:")
                    print(candlesticks[0])
                    return # Stop if we found data
            else:
                print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    # 1. Test with yesterday's closed market
    test_endpoint(CLOSED_TICKER, "Closed Market (Yesterday)")
    
    # 2. Test with an active market
    print("\nFetching active ticker...")
    active_ticker = get_active_ticker()
    print(f"Active ticker: {active_ticker}")
    if active_ticker:
        test_endpoint(active_ticker, "Active Market (Today)")
