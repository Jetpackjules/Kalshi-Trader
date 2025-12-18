from fetch_orderbook import get_markets_by_date
from datetime import datetime, timezone, timedelta

print("Debugging NOV19 fetch...")
markets = get_markets_by_date("NOV19")
print(f"Found {len(markets)} markets for NOV19")

if not markets:
    # Print what the filter was doing
    date_str = "NOV19"
    month_str = date_str[:3]
    day_str = date_str[3:]
    month_num = datetime.strptime(month_str, "%b").month
    day_num = int(day_str)
    year = 2025
    
    target_date = datetime(year, month_num, day_num)
    close_date = target_date + timedelta(days=1)
    
    min_ts = int(close_date.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc).timestamp())
    max_ts = int(close_date.replace(hour=12, minute=0, second=0, tzinfo=timezone.utc).timestamp())
    
    print(f"Filter Window (UTC): {datetime.fromtimestamp(min_ts, tz=timezone.utc)} to {datetime.fromtimestamp(max_ts, tz=timezone.utc)}")
    print(f"Min TS: {min_ts}")
    print(f"Max TS: {max_ts}")
    
    # Try fetching WITHOUT filters to see what the actual close time is for a NOV19 market
    print("\nFetching ALL markets to find NOV19 candidates...")
    import requests
    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    url = f"{BASE_URL}/markets?series_ticker=KXHIGHNY&limit=300&status=closed"
    resp = requests.get(url)
    all_markets = resp.json().get("markets", [])
    
    found = []
    for m in all_markets:
        if "NOV19" in m['ticker']:
            found.append(m)
            
    print(f"Found {len(found)} markets with 'NOV19' in ticker via broad fetch.")
    if found:
        m = found[0]
        print(f"Sample: {m['ticker']}")
        print(f"Close Time: {m.get('close_time')}")
        # Parse close time
        close_ts = datetime.fromisoformat(m['close_time'].replace('Z', '+00:00')).timestamp()
        print(f"Close TS: {int(close_ts)}")
