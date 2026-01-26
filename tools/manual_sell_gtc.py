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

def manual_sell_gtc():
    print("--- Manual Sell GTC Test ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # Target: Sell 2 YES of KXHIGHNY-26JAN24-T16 (We own 10)
    ticker = "KXHIGHNY-26JAN24-T16"
    qty = 2
    price = 5 # Sell YES at 5c (Limit)
    
    print(f"\n[Test] Action: SELL, Side: YES, Qty: {qty}, Price: {price}, GTC (No ReduceOnly)")
    
    payload = {
        "action": "sell",
        "ticker": ticker,
        "count": qty,
        "type": "limit",
        "side": "yes",
        "yes_price": price,
        # "reduce_only": False, # Default
        # "time_in_force": "good_till_canceled" # Default
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
    manual_sell_gtc()
