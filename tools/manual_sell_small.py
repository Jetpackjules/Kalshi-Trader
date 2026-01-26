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

def manual_sell_small():
    print("--- Manual Sell Small (2) Test ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # Target: Sell 2 YES of KXHIGHNY-26JAN24-B22.5
    ticker = "KXHIGHNY-26JAN24-B22.5"
    qty = 2
    
    # We want to "Market Sell" (hit the bid).
    # Current Bid is likely 1c or 2c.
    # To be safe, we Limit Sell at 1c (Buy NO at 99c).
    # This ensures it fills if there is ANY buyer.
    
    price = 1 # Sell YES at 1c
    no_price = 100 - price # Buy NO at 99c
    
    print(f"\n[Test] Action: BUY NO (Sell YES), Qty: {qty}, Price: {no_price} (YES @ {price}), ReduceOnly+IoC")
    
    payload = {
        "action": "buy",
        "ticker": ticker,
        "count": qty,
        "type": "limit",
        "side": "no",
        "no_price": no_price,
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
    manual_sell_small()
