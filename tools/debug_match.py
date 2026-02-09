
import pandas as pd
import datetime

fills_path = "vm_logs/unified_engine_out/fills.csv"
debug_path = "vm_logs/unified_engine_out/trade_debug.csv"

def main():
    # Load Fills
    df_fills = pd.read_csv(fills_path, header=None)
    df_fills.rename(columns={0: 'time', 1: 'ticker', 2: 'side', 3: 'price', 4: 'qty', 5: 'liquidity'}, inplace=True)
    df_fills['dt'] = pd.to_datetime(df_fills['time'], utc=True)
    
    # Target Fill: ~14:03 on Feb 6
    # Let's find the specific row dynamically
    print("Fills Head:")
    print(df_fills.head())
    print("Fills Tail:")
    print(df_fills.tail())
    
    # Strip whitespace from ticker
    df_fills['ticker'] = df_fills['ticker'].astype(str).str.strip()
    
    target = df_fills[df_fills['time'].astype(str).str.contains("14:03")]
    if target.empty:
        print("Could not find 14:03 fill")
        return
        
    fill_row = target.iloc[0]
    target_time = fill_row['dt']
    
    print("--- Target Fill ---")
    print(fill_row)
    
    # Load Debug
    df_debug = pd.read_csv(debug_path, header=None)
    df_debug['dt'] = pd.to_datetime(df_debug[1], utc=True, errors='coerce')
    
    print("\n--- Debug Rows around Window ---")
    # Filter +/- 5 minutes
    window_start = target_time - pd.Timedelta(minutes=5)
    window_end = target_time + pd.Timedelta(minutes=5)
    
    # Debug the parsing
    # print(df_debug['dt'].head())
    
    mask = (df_debug['dt'] >= window_start) & (df_debug['dt'] <= window_end)
    nearby = df_debug[mask]
    
    print(f"Found {len(nearby)} debug logs in window.")
    if not nearby.empty:
        # Col 6 is ticker, Col 7 is Action?
        print(nearby[[1, 6]].to_string()) 
        
    # Check exact match failure
    print("\n--- Ticker Check ---")
    fill_ticker = fill_row['ticker']
    matches = nearby[nearby[6] == fill_ticker]
    print(f"Ticker matches: {len(matches)}")
    if matches.empty:
        print(f"Fill Ticker: '{fill_ticker}'")
        if not nearby.empty:
            print(f"Debug Ticker Sample: '{nearby.iloc[0][6]}'")
    else:
        print("Timestamps of matches:")
        print(matches['dt'])
        print("\nDiff to Fill Time:")
        print((matches['dt'] - target_time).dt.total_seconds())

if __name__ == "__main__":
    main()
