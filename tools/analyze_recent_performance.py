import sys
import os
import json
import time
from datetime import datetime, timedelta

# Add root to path
sys.path.append(os.getcwd())

try:
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), ".."))
    from server_mirror.unified_engine.adapters import LiveAdapter, create_headers, API_URL

def analyze_performance():
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

    # Fetch fills for last 48 hours
    print("\n[1] Fetching Recent Fills (Last 100)...")
    path = "/trade-api/v2/portfolio/fills?limit=100" 
    headers = create_headers(adapter.private_key, "GET", path)
    resp = adapter._session.get(API_URL + path, headers=headers)
    
    if resp.status_code != 200:
        print(f"Error fetching fills: {resp.text}")
        return

    fills = resp.json().get("fills", [])
    print(f"Fetched {len(fills)} fills.")
    
    # Analyze
    total_volume = 0
    total_fees = 0 # API doesn't always give fees in fills, might need to estimate
    
    # Group by Ticker
    by_ticker = {}
    
    for f in fills:
        ticker = f.get("ticker")
        side = f.get("side")
        qty = f.get("count")
        price = f.get("yes_price") or f.get("no_price")
        ts = f.get("created_time")
        
        if ticker not in by_ticker:
            by_ticker[ticker] = {"buy_qty": 0, "buy_cost": 0, "sell_qty": 0, "sell_cost": 0, "net_qty": 0}
            
        # Cost = Price * Qty
        cost = (price / 100.0) * qty
        total_volume += cost
        
        # Estimate Fee (Taker: 0.35%? Maker: 0.2%? Or Convex?)
        # Let's assume standard 0.7% max for now or just ignore fees for gross PnL
        
        # Logic:
        # If we BOUGHT YES -> Buy
        # If we SOLD YES -> Sell (API might show as "sell" side? or "buy no"?)
        # Kalshi V2 API usually shows "buy" side "yes" or "no".
        # "buy no" is effectively "short yes" but distinct.
        
        # Let's just track "Money In" vs "Money Out" per ticker
        # Money Out (Spent) = Cost
        # Money In (Received) = ? (Only if we sell?)
        # Wait, we only BUY in this strategy (Buy YES or Buy NO).
        # We rely on SETTLEMENT for profit?
        # Or does the strategy SELL?
        # SimpleMarketMaker ONLY buys YES and buys NO. It never sends "sell" orders.
        # It relies on netting or settlement.
        # So all fills are "buys".
        # PnL comes from:
        # 1. Buying YES at 40, Buying NO at 55 -> Net Cost 95 -> Payoff 100 -> Profit 5.
        # 2. Buying YES at 40, Settlement at 100 -> Profit 60.
        # 3. Buying YES at 40, Settlement at 0 -> Loss 40.
        
        by_ticker[ticker]["buy_cost"] += cost
        by_ticker[ticker]["buy_qty"] += qty
        
        # Check if it's YES or NO
        if side == "yes":
            by_ticker[ticker]["net_qty"] += qty # Long YES
        else:
            by_ticker[ticker]["net_qty"] -= qty # Long NO = Short YES (approx)

    print("\n--- Analysis by Ticker (Last 100 Fills) ---")
    print(f"{'Ticker':<25} | {'Vol ($)':<8} | {'Count':<5} | {'Avg Price':<6}")
    print("-" * 60)
    
    for t, data in by_ticker.items():
        avg_price = (data["buy_cost"] / data["buy_qty"]) * 100 if data["buy_qty"] > 0 else 0
        print(f"{t:<25} | ${data['buy_cost']:<8.2f} | {data['buy_qty']:<5} | {avg_price:<6.1f}")

    print("\n--- Total Volume ---")
    print(f"Total Spent on New Positions: ${total_volume:.2f}")
    
    # Check Settlements
    print("\n[2] Checking Settlements (Last 100)...")
    path = "/trade-api/v2/portfolio/settlements?limit=100"
    headers = create_headers(adapter.private_key, "GET", path)
    resp = adapter._session.get(API_URL + path, headers=headers)
    
    recent_settlements = []
    if resp.status_code == 200:
        settlements = resp.json().get("settlements", [])
        print(f"Found {len(settlements)} settlements.")
        total_payout = 0
        
        # Sort by time descending
        settlements.sort(key=lambda x: x.get("settled_time"), reverse=True)
        
        print(f"{'Time':<20} | {'Ticker':<25} | {'Payout ($)':<10}")
        print("-" * 60)
        
        for s in settlements[:20]: # Show top 20 recent
            payout = s.get("payout", 0)
            payout_usd = payout / 100.0
            total_payout += payout_usd
            ts = s.get("settled_time", "")[:19].replace("T", " ")
            print(f"{ts:<20} | {s.get('ticker'):<25} | ${payout_usd:<10.2f}")
            recent_settlements.append(s)
            
        # Calculate total payout from ALL fetched (last 100)
        full_total_payout = sum(s.get("payout", 0) for s in settlements) / 100.0
        print(f"\nTotal Settlement Payouts (Last 100): ${full_total_payout:.2f}")
    else:
        print(f"Could not fetch settlements: {resp.status_code}")

    print("\n--- Analysis by Ticker (Last 100 Fills) ---")
    print(f"{'Ticker':<25} | {'Vol ($)':<8} | {'Count':<5} | {'Avg Price':<6} | {'Net Qty':<6}")
    print("-" * 70)
    
    for t, data in by_ticker.items():
        avg_price = (data["buy_cost"] / data["buy_qty"]) * 100 if data["buy_qty"] > 0 else 0
        print(f"{t:<25} | ${data['buy_cost']:<8.2f} | {data['buy_qty']:<5} | {avg_price:<6.1f} | {data['net_qty']:<6}")

    print("\n--- Total Volume ---")
    print(f"Total Spent on New Positions: ${total_volume:.2f}")
    if 'full_total_payout' in locals():
        print(f"Total Received from Settlements: ${full_total_payout:.2f}")
        print(f"Net Cash Flow (approx): ${full_total_payout - total_volume:.2f}")

if __name__ == "__main__":
    analyze_performance()
