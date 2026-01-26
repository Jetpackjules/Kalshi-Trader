import sys
import os
import json
import time
from datetime import datetime

# Add root to path
sys.path.append(os.getcwd())

try:
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), ".."))
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL

def manual_sell_native():
    print("--- Manual Native Sell (2) Test ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--qty", type=int, default=1)
    parser.add_argument("--price", type=int, default=1)
    args = parser.parse_args()

    # Target: Sell YES
    ticker = args.ticker
    qty = args.qty
    price = args.price
    
    print(f"\n[Test] Action: SELL, Side: YES, Qty: {qty}, Price: {price}, ReduceOnly+IoC")
    
    payload = {
        "action": "sell",
        "ticker": ticker,
        "count": qty,
        "type": "limit",
        "side": "yes",
        "yes_price": price,
        "reduce_only": True,
        "time_in_force": "immediate_or_cancel"
    }
    
    path = "/trade-api/v2/portfolio/orders"
    headers = create_headers(adapter.private_key, "POST", path)
    
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        resp = adapter._session.post(API_URL + path, headers=headers, json=payload)
        print(f"Response Code: {resp.status_code}")
        try:
            print(f"Response Body: {json.dumps(resp.json(), indent=2)}")
        except:
            print(f"Response Text: {resp.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    manual_sell_native()
