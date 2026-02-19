import sys
import os
import json
from datetime import datetime

# Add root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "server_mirror"))

try:
    from server_mirror.unified_engine.adapters import LiveAdapter
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), ".."))
    sys.path.append(os.path.join(os.getcwd(), "..", "server_mirror"))
    from server_mirror.unified_engine.adapters import LiveAdapter

def check_orders():
    print("--- Checking Pending Orders ---")
    
    key_path = "kalshi_prod_private_key.pem"
    if not os.path.exists(key_path):
        key_path = os.path.expanduser("~/kalshi_prod_private_key.pem")
    
    print(f"Using Key: {key_path}")
    
    # Monkey-patch cancel_all_orders to prevent wiping user's manual order
    original_cancel_all = LiveAdapter.cancel_all_orders
    LiveAdapter.cancel_all_orders = lambda self: print("DEBUG: Skipped startup cancellation.")
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # Fetch all orders (ticker=None) if supported, or try the specific ticker
    # The adapter interface usually allows filtering.
    # Let's try to get ALL orders if possible, or iterate a known list if needed.
    # Looking at engine usage: adapter.get_open_orders(ticker, ...)
    # Let's try passing None for ticker.
    
    print("Fetching ALL Open/Resting Orders (Portfolio Wide)...")
    found_orders = []
    
    # Manually fetch both statuses since get_open_orders_all might only do 'open'
    # We use the internal session if available, or just rely on the adapter method if it does both.
    # Looking at the code, get_open_orders_all only does 'open'.
    # So let's reproduce the fetch logic here for 'resting' too or just use the private method if we can.
    # actually, let's just use the adapter's session to fetch directly to be sure.
    
    session = adapter._session
    # base_url = adapter.API_URL <- Broken (API_URL is module level)
    # Actually, API_URL is a global in adapters.py, likely not on instance.
    # But LiveAdapter has self._session.
    # We need to import API_URL and create_headers from adapters to do this manually.
    # Or... we can just monkeypatch get_open_orders_all in the script if we want, or just call the API using the session.
    
    # Simpler: The adapter has 'cancel_all_orders' which fetches both.
    # But that cancels.
    # Let's just define a helper here to fetch.
    
    from server_mirror.unified_engine.adapters import API_URL, create_headers
    
    for status in ["open", "resting"]:
        path = f"/trade-api/v2/portfolio/orders?status={status}"
        headers = create_headers(adapter.private_key, "GET", path)
        try:
            resp = session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                orders = data.get("orders", [])
                print(f"Status '{status}': Found {len(orders)}")
                found_orders.extend(orders)
            else:
                print(f"Status '{status}': API Error {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Status '{status}': Exception {e}")

    if not found_orders:
        print("No open orders found in ENTIRE portfolio.")
    else:
        print(f"\nFound {len(found_orders)} Open/Resting Orders:")
        for o in found_orders:
            print(json.dumps(o, indent=2))
            
    print("\n--- Verifying Engine Visibility (adapter.get_open_orders) ---")
    # This is what the Engine calls. It should use the cache we just populated or fetch fresh.
    # We want to confirm it returns the order for T40.
    t40_orders = adapter.get_open_orders("KXHIGHNY-26FEB19-T40", {}, datetime.now())
    if t40_orders:
        print(f"SUCCESS: Engine sees {len(t40_orders)} orders for T40!")
        for o in t40_orders:
             price = o.get('yes_price') or o.get('no_price')
             print(f"  - {o.get('action')} {o.get('side')} {o.get('remaining_count')} @ {price} (Status: {o.get('status')})")
    else:
        print("FAILURE: Engine does NOT see the order for T40!")                

if __name__ == "__main__":
    check_orders()
