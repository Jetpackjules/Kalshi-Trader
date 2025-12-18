from fetch_orderbook import get_markets_by_date
from fetch_history import get_full_history
import json

def inspect():
    print("Fetching NOV20 markets...")
    markets = get_markets_by_date("NOV20")
    
    print(f"Found {len(markets)} markets.")
    for m in markets:
        print(f" - {m['ticker']}")
    
    targets = ["KXHIGHNY-25NOV20-T45", "KXHIGHNY-25NOV20-T52"]
    
    for m in markets:
        if m['ticker'] in targets:
            print(f"\n=== {m['ticker']} ===")
            print(f"Title: {m.get('title')}")
            print(f"Subtitle: {m.get('subtitle')}")
            print(f"Yes Bid: {m.get('yes_bid')}, Yes Ask: {m.get('yes_ask')}")
            print(f"Close Time: {m.get('close_time')}")
            
            print("Fetching History...")
            history = get_full_history(m['ticker'])
            print(f"Found {len(history)} candles.")
            if history:
                # Print last 5 candles
                print("Last 5 candles:")
                for c in history[-5:]:
                    print(c)

if __name__ == "__main__":
    inspect()
