import sys
import os
import json
import time
import requests
from datetime import datetime, timedelta

# Add root to path to import adapters
sys.path.append(os.getcwd())

try:
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL
except ImportError:
    # Fallback if running from tools/
    sys.path.append(os.path.join(os.getcwd(), ".."))
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL

def check_status():
    print("--- Connecting to Kalshi API ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    if not os.path.exists(key_path):
        print(f"Error: Key file not found at {key_path}")
        return

    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # 1. Balance
    print("\n[1] Fetching Balance...")
    cash = adapter.get_cash()
    portfolio_value = adapter.get_portfolio_value()
    equity = cash + portfolio_value
    
    print(f"Cash:            ${cash:.2f}")
    print(f"Portfolio Value: ${portfolio_value:.2f}")
    print(f"Total Equity:    ${equity:.2f}")

    # 2. Positions
    print("\n[2] Fetching Positions...")
    positions = adapter.get_positions()
    total_pos_cost = 0.0
    
    if not positions:
        print("No open positions.")
    else:
        print(f"{'Ticker':<25} | {'Side':<4} | {'Qty':<5} | {'Cost':<8} | {'Value':<8}")
        print("-" * 65)
        for ticker, pos in positions.items():
            cost = pos.get("cost", 0.0)
            total_pos_cost += cost
            
            # Estimate Market Value
            last_price = pos.get("last_price", 0.0)
            qty = pos.get("yes", 0) + pos.get("no", 0)
            market_value = qty * last_price
            
            if pos.get("yes", 0) > 0:
                print(f"{ticker:<25} | {'YES':<4} | {pos['yes']:<5} | ${cost:<8.2f} | ${market_value:<8.2f}")
            if pos.get("no", 0) > 0:
                print(f"{ticker:<25} | {'NO':<4} | {pos['no']:<5} | ${cost:<8.2f} | ${market_value:<8.2f}")
    
    # 3. Open Orders (All)
    print("\n[3] Fetching Open Orders...")
    
    # Attempt 1: Generic Fetch (No status filter, just get recent)
    path = "/trade-api/v2/portfolio/orders" # Remove ?status=open to see everything
    headers = create_headers(adapter.private_key, "GET", path)
    resp = adapter._session.get(API_URL + path, headers=headers)
    
    orders = []
    if resp.status_code == 200:
        data = resp.json()
        all_orders = data.get("orders", [])
        print(f"DEBUG: Generic fetch (no filter) returned {len(all_orders)} orders.")
        # Filter for open/resting locally
        orders = [o for o in all_orders if o.get("status") in ("open", "resting", "pending")]
        print(f"DEBUG: Filtered to {len(orders)} open/resting orders.")
        
        if len(orders) == 0 and len(all_orders) > 0:
             print(f"DEBUG: Sample of non-open orders: {[o.get('status') for o in all_orders[:5]]}")

    else:
        print(f"DEBUG: Generic fetch failed: {resp.status_code} {resp.text}")

    # Attempt 2: Explicit Ticker Scan (if generic failed)
    if not orders:
        print("DEBUG: Scanning likely tickers for Jan 21 & Jan 22...")
        # Construct a list of likely tickers to check
        # We know the format: KXHIGHNY-DDMMMYY-T/BXX.X
        # Let's check a few common ones based on recent price (around 40)
        suspects = []
        for day in ["26JAN21", "26JAN22"]:
            for type in ["B", "T"]: # Below, Above (Wait, T is High?) No, T is "Ticket"? No, range.
                # Kalshi High NY tickers: KXHIGHNY-26JAN21-B40, T40?
                # Actually, let's look at the positions to guess the format.
                # From previous output: KXHIGHNY-26JAN21-B39.5
                pass
        
        # Actually, let's just use the tickers from the positions we found earlier + some neighbors
        known_tickers = list(positions.keys())
        # Add some neighbors
        for t in known_tickers:
            # e.g. ...-B39.5 -> try B39, B40, B38
            pass
            
        # Just check the known positions again, but verbose
        for ticker in known_tickers:
            path = f"/trade-api/v2/portfolio/orders?ticker={ticker}&status=open"
            headers = create_headers(adapter.private_key, "GET", path)
            resp = adapter._session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                found = resp.json().get("orders", [])
                if found:
                    print(f"DEBUG: Found {len(found)} orders for {ticker}")
                    orders.extend(found)
            time.sleep(0.05)

    tied_up_cash = 0.0
    order_count = len(orders)
    
    if not orders:
        print("No open orders found (after retry).")
    else:
        print(f"{'Ticker':<25} | {'Side':<4} | {'Price':<5} | {'Qty':<5} | {'Status':<10} | {' tied ($)':<10}")
        print("-" * 75)
        for o in orders:
            side = o.get("side", "yes")
            price = o.get("yes_price") if side == "yes" else o.get("no_price")
            qty = o.get("remaining_count", 0)
            status = o.get("status", "unknown")
            
            cost = 0.0
            if price is not None:
                cost = (price / 100.0) * qty
                tied_up_cash += cost
                
            print(f"{o.get('ticker'):<25} | {side.upper():<4} | {price:<5} | {qty:<5} | {status:<10} | ${cost:<10.2f}")

    # 4. Recent Fills
    print("\n[4] Fetching Recent Fills (Last 24h)...")
    # Endpoint: /trade-api/v2/portfolio/fills
    # Need to check if this endpoint exists and works.
    # Assuming it does based on standard API patterns.
    path = "/trade-api/v2/portfolio/fills?limit=20" 
    headers = create_headers(adapter.private_key, "GET", path)
    resp = adapter._session.get(API_URL + path, headers=headers)
    
    if resp.status_code == 200:
        fills = resp.json().get("fills", [])
        if not fills:
            print("No recent fills.")
        else:
            print(f"{'Time':<20} | {'Ticker':<25} | {'Side':<4} | {'Price':<5} | {'Qty':<5}")
            print("-" * 70)
            for f in fills:
                # Time format: 2026-01-21T...
                ts = f.get("created_time", "")
                # Truncate or parse
                ts_short = ts[:19].replace("T", " ")
                
                print(f"{ts_short:<20} | {f.get('ticker'):<25} | {f.get('side', '').upper():<4} | {f.get('yes_price') or f.get('no_price'):<5} | {f.get('count'):<5}")
    else:
        print(f"Error fetching fills: {resp.text}")

    # Summary
    print("\n--- Summary ---")
    print(f"Available Cash:   ${cash:.2f}")
    print(f"Tied in Orders:   ${tied_up_cash:.2f}")
    print(f"Tied in Positions:${total_pos_cost:.2f}")
    print(f"True Free Cash:   ${max(0, cash - tied_up_cash):.2f}")

if __name__ == "__main__":
    check_status()
