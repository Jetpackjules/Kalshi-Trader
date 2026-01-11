import pandas as pd
import sys
import os

def compare_decisions(live_path, backtest_path):
    print(f"Live: {live_path}")
    print(f"Backtest: {backtest_path}")
    
    if not os.path.exists(live_path):
        print("Live file not found.")
        return
    if not os.path.exists(backtest_path):
        print("Backtest file not found.")
        return

    # Load logs
    # Columns typically: decision_time, ticker, decision_type, action, price, qty, ...
    live = pd.read_csv(live_path)
    backtest = pd.read_csv(backtest_path)

    # Normalize timestamps to nearest second for matching
    # The live bot might be slightly slower/faster than the backtest simulation time
    live['time_obj'] = pd.to_datetime(live['tick_time'])
    backtest['time_obj'] = pd.to_datetime(backtest['tick_time'])
    
    live = live.sort_values('time_obj')
    backtest = backtest.sort_values('time_obj')

    print(f"Live Rows: {len(live)}")
    print(f"Backtest Rows: {len(backtest)}")

    # Filter for only "desired" decisions (where the bot actually wanted to do something)
    # or compare all to see why one said "desired" and other didn't.
    
    # Let's look for cases where Live said BUY but Backtest didn't.
    live_buys = live[live['action'].str.contains('BUY', na=False)]
    print(f"Live Buys: {len(live_buys)}")
    
    for idx, row in live_buys.iterrows():
        t = row['time_obj']
        ticker = row['ticker']
        
        # Find matching backtest row (within 2 seconds)
        # We look for the same ticker around the same time
        window = pd.Timedelta(seconds=2)
        match = backtest[
            (backtest['ticker'] == ticker) & 
            (backtest['time_obj'] >= t - window) & 
            (backtest['time_obj'] <= t + window)
        ]
        
        if match.empty:
            print(f"\n[MISSING] Live BUY at {t} for {ticker} - No matching backtest decision found.")
            continue
            
        # Check if backtest also bought
        backtest_buy = match[match['action'].str.contains('BUY', na=False)]
        if backtest_buy.empty:
            print(f"\n[DIVERGENCE] Live BUY at {t} for {ticker}")
            print(f"   Live Reason: {row.get('decision_type')} | Price: {row.get('price')} | Qty: {row.get('qty')}")
            
            # What did the backtest do instead?
            # Print the nearest backtest row's details
            nearest = match.iloc[0] # Just take the first one found in window
            print(f"   Backtest: {nearest.get('decision_type')} | Action: {nearest.get('action')} | Reason: {nearest.get('reason') if 'reason' in nearest else 'N/A'}")
            
            # If we have extra debug columns, print them
            # Common columns: 'spread', 'mid', 'fair', 'edge', 'status'
            cols_to_show = ['mid', 'spread', 'fair', 'fair_prob', 'edge', 'edge_cents', 'required', 'status', 'reason']
            live_debug = {k: row.get(k) for k in cols_to_show if k in row}
            backtest_debug = {k: nearest.get(k) for k in cols_to_show if k in nearest}
            
            print(f"   Live Debug: {live_debug}")
            print(f"   Backtest Debug: {backtest_debug}")
            
            # Stop after a few examples
            if idx > 20: 
                break
        else:
            # They matched!
            pass

if __name__ == "__main__":
    if len(sys.argv) > 2:
        live_file = sys.argv[1]
        backtest_file = sys.argv[2]
    else:
        live_file = r"vm_logs\unified_engine_out\decision_intents.csv"
        # Default backtest output from generate_live_vs_backtest_graph.py
        backtest_file = r"unified_engine_out_snapshot_live\decision_intents.csv" 
    
    compare_decisions(live_file, backtest_file)
