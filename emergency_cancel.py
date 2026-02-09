import sys
import os
import time

# Add server_mirror to path
sys.path.append(os.path.join(os.getcwd(), "server_mirror"))

from unified_engine.adapters import LiveAdapter

def main():
    print("Initializing LiveAdapter...")
    # Key is in current directory
    key_path = "kalshi_prod_private_key.pem"
    if not os.path.exists(key_path):
        key_path = os.path.join(os.getcwd(), "kalshi_prod_private_key.pem")
    
    if not os.path.exists(key_path):
        print(f"CRITICAL: Key not found at {key_path}")
        return
        
    print(f"Using key: {key_path}")
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Failed to init adapter: {e}")
        return

    print("Fetching ALL open orders from API (Bypassing Cache)...")
    
    # 1. Try status=open
    from unified_engine.adapters import create_headers, API_URL
    
    orders = []
    
    for s in ["open", "resting"]:
        print(f"Querying status={s}...")
        path = f"/trade-api/v2/portfolio/orders?status={s}"
        headers = create_headers(adapter.private_key, "GET", path)
        try:
            resp = adapter._session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                found = data.get("orders", [])
                print(f"  Found {len(found)} orders.")
                orders.extend(found)
            else:
                print(f"  Failed: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"  Error: {e}")

    # Dedupe by ID
    unique_orders = {o["order_id"]: o for o in orders}
    orders = list(unique_orders.values())
        
    print(f"Total Unique Orders: {len(orders)}")
    
    if not orders:
        print("No ghost orders found. The account is clean.")
        return

    for o in orders:
        oid = o.get("order_id")
        ticker = o.get("ticker")
        side = o.get("side")
        qty = o.get("remaining_count") or o.get("count")
        price = o.get("yes_price") if side == "yes" else o.get("no_price")
        
        print(f"Ghost Found: {ticker} | {side.upper()} {qty} @ {price} | ID: {oid}")
        print(f"Cancelling {oid}...")
        adapter.cancel_order(oid)
        time.sleep(0.1) # Rate limit safety
    
    print("Done. All ghost orders cancelled.")

if __name__ == "__main__":
    main()
