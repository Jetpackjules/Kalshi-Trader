import sys
import os
import time

# Add root to path
sys.path.append(os.getcwd())

try:
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), ".."))
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL

def cancel_all():
    print("--- Cancelling ALL Orders ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # Fetch all orders
    path = "/trade-api/v2/portfolio/orders"
    headers = create_headers(adapter.private_key, "GET", path)
    resp = adapter._session.get(API_URL + path, headers=headers)
    
    if resp.status_code != 200:
        print(f"Failed to fetch orders: {resp.text}")
        return

    orders = resp.json().get("orders", [])
    print(f"Found {len(orders)} open orders.")
    
    for o in orders:
        oid = o.get("order_id")
        ticker = o.get("ticker")
        print(f"Cancelling {ticker} ({oid})...")
        adapter.cancel_order(oid)
        time.sleep(0.1) # Rate limit nice

    print("Done.")

if __name__ == "__main__":
    cancel_all()
