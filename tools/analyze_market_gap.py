
import pandas as pd
import datetime

# Target: KXHIGHNY-26FEB07
file_path = "vm_logs/market_logs/market_data_KXHIGHNY-26FEB07.csv"

def main():
    print(f"--- Analyzing {file_path} for 8c Gaps ---")
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print("File not found.")
        return

    # Columns: timestamp,market_ticker,best_yes_bid,best_yes_bid_qty,best_no_bid,best_no_bid_qty,implied_no_ask,implied_no_ask_size,implied_yes_ask,implied_yes_ask_size,last_trade_price
    
    # Parse timestamp
    df['dt'] = pd.to_datetime(df['timestamp'], utc=True)
    
    # Calculate Spread
    # Spread = Yes Ask - Yes Bid
    # implied_yes_ask is explicitly there.
    # But sometimes it's 0 or 100 which means empty? 
    # Let's check implied_yes_ask > 0 and < 100.
    
    # Filter for valid books
    mask = (df['implied_yes_ask'] < 100) & (df['best_yes_bid'] > 0)
    valid = df[mask].copy()
    
    valid['spread'] = valid['implied_yes_ask'] - valid['best_yes_bid']
    
    # Find gaps >= 8
    gaps = valid[valid['spread'] >= 8]
    
    print(f"Total rows: {len(df)}")
    print(f"Valid book rows: {len(valid)}")
    print(f"Rows with Spread >= 8c: {len(gaps)}")
    
    if not gaps.empty:
        print("\n--- Recent 8c Gaps ---")
        # Identify blocks of consecutive gaps
        # We can check time deltas.
        
        gaps['prev_dt'] = gaps['dt'].shift(1)
        gaps['time_diff'] = (gaps['dt'] - gaps['prev_dt']).dt.total_seconds()
        
        # New block if time diff > 1.5s (assuming ~1s polling/ws cadence)
        gaps['new_block'] = gaps['time_diff'] > 2.0
        gaps['block_id'] = gaps['new_block'].cumsum()
        
        durations = []
        
        # Group by block
        for block_id, group in gaps.groupby('block_id'):
            start = group['dt'].iloc[0]
            end = group['dt'].iloc[-1]
            duration = (end - start).total_seconds()
            
            # Get typical spread stats in this block
            avg_spread = group['spread'].mean()
            
            # Filter: Only significant blocks or specific time
            # if duration < 0.05: continue
            
            # Print detail
            # print(f"Gap Block #{block_id}:")
            # print(f"  Start: {start.strftime('%H:%M:%S.%f')}")
            # print(f"  End:   {end.strftime('%H:%M:%S.%f')}")
            # print(f"  Dur:   {duration:.3f}s")
            # print(f"  Avg Spread: {avg_spread:.1f}c")
            # print("-" * 30)
            
            durations.append(duration)
            
    if durations:
        s = pd.Series(durations)
        print("\n--- Gap Duration Stats (Spread >= 8c) ---")
        print(f"Count: {len(s)}")
        print(f"Mean:  {s.mean():.3f}s")
        print(f"Median: {s.median():.3f}s")
        print(f"Max:   {s.max():.3f}s")
        print(f"Min:   {s.min():.3f}s")
        print("\nPercentiles:")
        print(s.quantile([0.25, 0.5, 0.75, 0.90, 0.95, 0.99]))
        
        print(f"\n% > 0.5s: {(s > 0.5).mean() * 100:.1f}%")
        print(f"% > 2.0s: {(s > 2.0).mean() * 100:.1f}%")

if __name__ == "__main__":
    main()
