import requests

def test_fetch_markets():
    API_URL = "https://api.elections.kalshi.com/trade-api/v2"
    target_date = "2026-02-23"
    
    print("Fetching active KXHIGHNY markets...")
    response = requests.get(f"{API_URL}/markets", params={"series_ticker": "KXHIGHNY", "status": "open"})
    if response.status_code == 200:
        data = response.json()
        markets = data.get("markets", [])
        print(f"Found {len(markets)} active markets.")
        # Filter for our target date
        target_tickers = []
        for market in markets:
            ticker = market.get("ticker", "")
            if "FEB23" in ticker:
                target_tickers.append(ticker)
        print(f"Markets for {target_date}: {target_tickers}")
        if markets:
            print(f"Keys: {list(markets[0].keys())}")
            print(f"yes_ask: {markets[0].get('yes_ask')} no_ask: {markets[0].get('no_ask')}")
    else:
        print(f"Error: {response.status_code}")

test_fetch_markets()
