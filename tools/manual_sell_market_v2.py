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

def manual_sell_market_v2():
    print("--- Manual Market Sell V2 Test ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # Target: Sell 50 YES of KXHIGHNY-26JAN24-B22.5
    ticker = "KXHIGHNY-26JAN24-B22.5"
    qty = 50
    
    # Test 1: Action "sell", Type "market", with yes_price (1c)
    print(f"\n[Test 1] Action: SELL, Type: MARKET, Price: 1c")
    payload = {
        "action": "sell",
        "ticker": ticker,
        "count": qty,
        "type": "market",
        "side": "yes",
        "yes_price": 1 # Try providing price even for market
    }
    send_request(adapter, payload)

    # Test 2: Action "buy", Side "no", Type "market", buy_max_cost
    # Cost for 50 NO at 99c = 4950 cents. Add buffer -> 5000.
    print(f"\n[Test 2] Action: BUY NO, Type: MARKET, Max Cost: 5000")
    payload_buy = {
        "action": "buy",
        "ticker": ticker,
        "count": qty,
        "type": "market",
        "side": "no",
        "buy_max_cost": 5000
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
    manual_sell_market_v2()
