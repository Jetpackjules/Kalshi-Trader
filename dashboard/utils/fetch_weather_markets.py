import requests
import datetime
from datetime import timedelta
import time

SERIES_TICKER = "KXHIGHNY"

# Bases from React code
KALSHI_BASES = [
    "https://api.elections.kalshi.com/trade-api/v2",
    "https://trading-api.kalshi.com/trade-api/v2",
]

def get_kalshi_date_str(date_obj):
    """Formats date as YYMMMdd (e.g., 25AUG26)."""
    year = str(date_obj.year)[-2:]
    month = date_obj.strftime("%b").upper()
    day = str(date_obj.day).zfill(2)
    return f"{year}{month}{day}"

def fetch_market_data(days_back=5):
    today = datetime.date.today()
    dates = [today - timedelta(days=i) for i in range(days_back)]
    
    all_markets = []

    for date in dates:
        date_str = get_kalshi_date_str(date)
        event_ticker = f"{SERIES_TICKER}-{date_str}"
        
        markets = []
        for base in KALSHI_BASES:
            markets_url = f"{base}/markets?event_ticker={event_ticker}&limit=500"
            try:
                response = requests.get(markets_url, timeout=10)
                if response.ok:
                    data = response.json()
                    markets = data.get("markets", [])
                    if markets:
                        break
            except requests.exceptions.RequestException:
                continue

        if not markets:
            print(f"{date_str:<12} No markets found.")
            continue

        for market in markets:
            market['date_str'] = date_str
            all_markets.append(market)
            
    return all_markets

def parse_candles_any(data):
    """
    Robust parser for various candle/trade response formats, ported from React.
    """
    if not data:
        return []
        
    # Helper to normalize keys
    def to_candle(x):
        # React: t ?? time ?? timestamp ?? start ?? start_time ...
        t = x.get('t') or x.get('time') or x.get('timestamp') or x.get('start') or x.get('start_time') or x.get('created_time') or x.get('executed_at')
        if t is None: return None
        
        # Handle timestamps
        if isinstance(t, str):
            try:
                ts = datetime.datetime.fromisoformat(t.replace('Z', '+00:00')).timestamp()
            except:
                return None
        else:
            ts = t if t > 1e12 else t * 1000 # Ensure ms if it's int
            ts = ts / 1000.0 # Convert to seconds for datetime
            
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)

        # Price
        # React: close ?? c ?? close_price ?? close_cents ?? price ...
        p = x.get('close') or x.get('c') or x.get('close_price') or x.get('price') or x.get('last_price') or x.get('yes_price')
        if p is None: return None
        
        # Convert cents to dollars if > 1 (heuristic from React code)
        price = float(p)
        if price > 1.5: # Assuming price is 0-1 for probability, or 0-100 for cents. 1.5 is safe threshold.
            price = price / 100.0
            
        return {"time": dt, "price": price}

    candidates = []
    
    # Direct list
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        # Check common keys
        for k in ["candles", "bars", "items", "results", "list", "trades"]:
            if k in data and isinstance(data[k], list):
                candidates = data[k]
                break
        # Check nested data
        if not candidates and "data" in data:
            if isinstance(data["data"], list):
                candidates = data["data"]
            elif isinstance(data["data"], dict):
                 for k in ["candles", "bars", "items", "results", "list", "trades"]:
                    if k in data["data"] and isinstance(data["data"][k], list):
                        candidates = data["data"][k]
                        break

    results = []
    for item in candidates:
        c = to_candle(item)
        if c:
            results.append(c)
            
    return sorted(results, key=lambda x: x['time'])

def fetch_market_history(ticker, date_obj):
    """
    Fetches historical data using logic ported from React.
    """
    start_dt = datetime.datetime(date_obj.year, date_obj.month, date_obj.day, tzinfo=datetime.timezone.utc)
    end_dt = start_dt + timedelta(days=1)
    
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Paths from React code
    paths = [
        f"/candles?market_ticker={ticker}&interval=1m&start_time={start_iso}&end_time={end_iso}",
        f"/markets/{ticker}/candles?interval=1m&start_time={start_iso}&end_time={end_iso}",
        f"/trades?market_ticker={ticker}&start_time={start_iso}&end_time={end_iso}&limit=5000",
        f"/markets/{ticker}/trades?limit=5000",
        f"/trades?market_ticker={ticker}&limit=5000"
    ]
    
    headers = {
        "Accept": "application/json",
        # Mimic browser
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://kalshi.com",
        "Referer": "https://kalshi.com/"
    }

    import urllib.parse

    # Add relay logic
    # React: https://api.allorigins.win/raw?url=${encodeURIComponent(url)}
    
    attempts = []
    for base in KALSHI_BASES:
        for path in paths:
            direct_url = f"{base}{path}"
            attempts.append(direct_url)
            
            # Add relay version
            # React: https://thingproxy.freeboard.io/fetch/${url}
            relay_url = f"https://thingproxy.freeboard.io/fetch/{direct_url}"
            attempts.append(relay_url)

    for url in attempts:
        print(f"Trying: {url}")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            if response.ok:
                data = response.json()
                parsed = parse_candles_any(data)
                if parsed:
                    print(f"Found {len(parsed)} candles")
                    return parsed
                else:
                    print("Parsed empty")
            else:
                print(f"Error: {response.text[:200]}")
        except Exception as e:
            print(f"Failed {url}: {e}")
            continue
                
    return []

def print_market_data(markets):
    print(f"{'Date':<12} {'Market Ticker':<25} {'Title':<30} {'Status':<10} {'Last Price':<10} {'Volume':<10}")
    print("-" * 100)
    
    for market in markets:
        date_str = market.get('date_str', 'N/A')
        ticker = market.get("ticker")
        title = market.get("title")
        status = market.get("status")
        last_price = market.get("last_price", 0) / 100.0
        volume = market.get("volume", 0)
        
        print(f"{date_str:<12} {ticker:<25} {title:<30} {status:<10} ${last_price:<9.2f} {volume:<10}")

if __name__ == "__main__":
    data = fetch_market_data()
    print_market_data(data)
