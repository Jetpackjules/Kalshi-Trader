import requests

TICKER = "KXHIGHNY-25NOV20-T52"
DOMAINS = [
    "https://api.elections.kalshi.com/trade-api/v2",
    "https://trading-api.kalshi.com/trade-api/v2",
    "https://demo-api.kalshi.co/trade-api/v2"
]

def check_history():
    print(f"Checking history for {TICKER}...")
    
    # Timestamps for Nov 20
    start_ts = 1732060800
    end_ts = 1732147200
    
    for base_url in DOMAINS:
        print(f"\n--- Testing {base_url} ---")
        
        endpoints = [
            f"/markets/{TICKER}/candles?interval=1h&start_time={start_ts}&end_time={end_ts}",
            f"/markets/{TICKER}/trades?limit=10",
            f"/series/KXHIGHNY/markets/{TICKER}/candles?interval=1h"
        ]
        
        for ep in endpoints:
            url = f"{base_url}{ep}"
            try:
                print(f"GET {ep}")
                res = requests.get(url, timeout=5)
                print(f"  Status: {res.status_code}")
                if res.status_code == 200:
                    print(f"  SUCCESS! Data: {res.text[:100]}...")
                elif res.status_code == 401:
                    print("  401 Unauthorized (Needs auth?)")
                elif res.status_code == 403:
                    print("  403 Forbidden")
                elif res.status_code == 404:
                    print("  404 Not Found")
            except Exception as e:
                print(f"  Error: {e}")

if __name__ == "__main__":
    check_history()
