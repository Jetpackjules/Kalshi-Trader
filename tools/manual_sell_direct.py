import sys
import os
import time
from datetime import datetime

# Add root to path
sys.path.append(os.getcwd())

try:
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), ".."))
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL

def manual_sell_direct():
    print("--- Manual Direct SELL Test ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # Target: Sell 50 YES of KXHIGHNY-26JAN24-B22.5
    ticker = "KXHIGHNY-26JAN24-B22.5"
    qty = 50
    price = 5 # Sell YES at 5c
    
    print(f"Target: {ticker}")
    print(f"Action: SELL YES (Direct)")
    print(f"Qty: {qty}")
    print(f"Limit Price: {price}c")
    
    # Construct Payload manually to force "sell" action
    payload = {
        "action": "sell",
        "ticker": ticker,
        "count": qty,
        "type": "limit",
        "side": "yes", # Selling YES
        "yes_price": price,
        # "no_price": ...
    }
    
    print(f"Payload: {payload}")
    
    path = "/trade-api/v2/portfolio/orders"
    headers = create_headers(adapter.private_key, "POST", path)
    
    try:
        resp = adapter._session.post(API_URL + path, headers=headers, json=payload)
        print(f"Response Code: {resp.status_code}")
        print(f"Response Text: {resp.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    manual_sell_direct()
