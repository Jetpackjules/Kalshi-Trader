import sys
import os
import json
import time

# Add root to path
sys.path.append(os.getcwd())

try:
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), ".."))
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL

def list_open_orders():
    print("--- Listing Open Orders ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    path = "/trade-api/v2/portfolio/orders"
    headers = create_headers(adapter.private_key, "GET", path)
    resp = adapter._session.get(API_URL + path, headers=headers)
    
    if resp.status_code != 200:
        print(f"Failed to fetch orders: {resp.text}")
        return

    orders = resp.json().get("orders", [])
    print(f"Total Orders Fetched: {len(orders)}")
    
    resting_orders = [o for o in orders if o.get("status") == "resting"]
    print(f"Total RESTING Orders: {len(resting_orders)}")
    
    for i, o in enumerate(orders[:5]):
        print(f"\n[Order {i+1}]")
        print(f"Ticker: {o.get('ticker')}")
        print(f"Action: {o.get('action')}")
        print(f"Side: {o.get('side')}")
        print(f"Type: {o.get('type')}")
        print(f"Status: {o.get('status')}")
        print(f"Created: {o.get('created_time')}")
        print(f"Updated: {o.get('last_update_time')}")
        print(f"Price (YES): {o.get('yes_price')}")
        print(f"Price (NO): {o.get('no_price')}")
        print(f"Qty: {o.get('remaining_count')}")

if __name__ == "__main__":
    list_open_orders()
