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

def manual_sell_ioc():
    print("--- Manual Sell IoC Test ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # Target: Sell 50 YES of KXHIGHNY-26JAN24-B22.5
    ticker = "KXHIGHNY-26JAN24-B22.5"
    qty = 50
    price = 1 # Sell YES at 1c (Market Dump) to ensure fill if anyone is buying
    
    # Test 1: Action "sell", Side "yes", Reduce Only, IoC
    print(f"\n[Test 1] Action: SELL, Side: YES, Reduce Only: True, IoC")
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
    send_request(adapter, payload)

    # Test 2: Action "buy", Side "no", Reduce Only, IoC (Netting)
    # Buy NO at 99c = Sell YES at 1c
    no_price = 100 - price
    print(f"\n[Test 2] Action: BUY, Side: NO, Reduce Only: True, IoC, Price: {no_price}")
    payload_buy = {
        "action": "buy",
        "ticker": ticker,
        "count": qty,
        "type": "limit",
        "side": "no",
        "no_price": no_price,
        "reduce_only": True,
        "time_in_force": "immediate_or_cancel"
    }
    send_request(adapter, payload_buy)

def send_request(adapter, payload):
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
    manual_sell_ioc()
