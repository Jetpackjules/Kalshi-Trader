import requests
import datetime
import json
import kalshi_python

# Configuration
DATE_STR = "25NOV18" # Nov 18, 2025
EVENT_TICKER = f"KXHIGHNY-{DATE_STR}"
BASES = [
    "https://api.elections.kalshi.com/trade-api/v2",
    "https://trading-api.kalshi.com/trade-api/v2"
]

def get_markets():
    print(f"Fetching markets for {EVENT_TICKER}...")
    for base in BASES:
        url = f"{base}/markets?event_ticker={EVENT_TICKER}&limit=500"
        try:
            print(f"Trying {url}")
            res = requests.get(url)
            if res.ok:
                data = res.json()
                markets = data.get("markets", [])
                print(f"Found {len(markets)} markets on {base}")
                if markets:
                    return markets
            else:
                print(f"Failed: {res.status_code} - {res.text[:100]}")
        except Exception as e:
            print(f"Error: {e}")
    return []

def fetch_history_public(ticker):
    print(f"\nFetching history (Public) for {ticker}...")
    
    # Time range for Nov 18
    # Assuming 2025 based on ticker
    start_dt = datetime.datetime(2025, 11, 18, tzinfo=datetime.timezone.utc)
    end_dt = start_dt + datetime.timedelta(days=1)
    
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    paths = [
        f"/candles?market_ticker={ticker}&interval=1m&start_time={start_iso}&end_time={end_iso}",
        f"/markets/{ticker}/candles?interval=1m&start_time={start_iso}&end_time={end_iso}",
        f"/trades?market_ticker={ticker}&start_time={start_iso}&end_time={end_iso}&limit=5000",
        f"/markets/{ticker}/trades?limit=5000"
    ]
    
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://kalshi.com",
        "Referer": "https://kalshi.com/"
    }
    
    for base in BASES:
        for path in paths:
            url = f"{base}{path}"
            print(f"GET {url}")
            try:
                res = requests.get(url, headers=headers, timeout=5)
                print(f"Status: {res.status_code}")
                if res.ok:
                    data = res.json()
                    # Check for candles/trades
                    if "candles" in data or "trades" in data:
                        print("SUCCESS! Found data.")
                        return data
                    elif "data" in data and ("candles" in data["data"] or "trades" in data["data"]):
                        print("SUCCESS! Found data (nested).")
                        return data
            except Exception as e:
                print(f"Error: {e}")
    return None

def fetch_history_sdk(ticker):
    print(f"\nFetching history (SDK) for {ticker}...")
    
    key_id = "7a266d00-7db2-4c35-90e0-477b739fac06"
    try:
        with open("kalshi_private_key.pem", "r") as f:
            private_key = f.read()
    except:
        print("No private key file found.")
        return

    try:
        config = kalshi_python.Configuration()
        config.api_key_id = key_id
        config.private_key = private_key
        
        client = kalshi_python.KalshiClient(configuration=config)
        markets_api = kalshi_python.MarketsApi(client)
        
        print("Inspecting get_market_candlesticks...")
        try:
            with open("sdk_help_full.txt", "w") as hf:
                import pydoc
                hf.write(pydoc.render_doc(markets_api.get_market_candlesticks))
        except Exception as e:
            print(f"Help Error: {e}")
        
        start_dt = datetime.datetime(2025, 11, 18, tzinfo=datetime.timezone.utc)
        end_dt = start_dt + datetime.timedelta(days=1)
        
        print("Inspecting MarketsApi methods...")
        print(dir(markets_api))
        
        # Try get_market_candlesticks
        print("Calling get_market_candlesticks...")
        try:
            # ... (existing call)
            res = markets_api.get_market_candlesticks(
                ticker="KXHIGHNY",
                market_ticker=ticker,
                start_ts=int(start_dt.timestamp()),
                end_ts=int(end_dt.timestamp()),
                period_interval=1
            )
            # print("SDK Candles (1) Success!")
            # print(res)
            return res
                
        except Exception as e:
            print(f"Error checking {ticker}: {e}")
            
    except Exception as e:
        print(f"SDK Setup Error: {e}")

def main():
    markets = get_markets()
    if not markets:
        print("No markets found for Nov 18.")
        return

    print(f"\nFound {len(markets)} markets. Checking for data...")
    
    for m in markets:
        ticker = m['ticker']
        print(f"\nChecking Market: {ticker}")
        
        # Try SDK
        try:
            # We need to re-initialize SDK or reuse it. 
            # For simplicity, let's just call fetch_history_sdk which re-inits (inefficient but fine for script)
            # Actually, let's refactor fetch_history_sdk to take the client/api as arg? 
            # No, just call it.
            res = fetch_history_sdk(ticker)
            
            # Check if we got valid data
            found_data = False
            if res and hasattr(res, 'candlesticks') and res.candlesticks:
                for c in res.candlesticks:
                    if c.volume and c.volume > 0:
                        if c.close is not None:
                            print(f"FOUND DATA for {ticker}!")
                            print(f"Candle: {c}")
                            found_data = True
                            break
                        else:
                            print(f"Found volume for {ticker} but no price. Skipping.")
            
            if found_data:
                print("Stopping search as data was found.")
                break
                
        except Exception as e:
            print(f"Error checking {ticker}: {e}")

if __name__ == "__main__":
    main()
