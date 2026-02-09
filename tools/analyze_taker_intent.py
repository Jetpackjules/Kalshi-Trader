
import pandas as pd
import datetime
import os

fills_path = "vm_logs/unified_engine_out/fills.csv"
debug_path = "vm_logs/unified_engine_out/trade_debug.csv"

def main():
    if not os.path.exists(fills_path) or not os.path.exists(debug_path):
        print("Missing logs.")
        return

    # Load Fills
    df_fills = pd.read_csv(fills_path, header=None)
    df_fills.rename(columns={0: 'time', 1: 'ticker', 2: 'side', 3: 'price', 4: 'qty', 5: 'liquidity'}, inplace=True)
    df_fills['dt'] = pd.to_datetime(df_fills['time'], utc=True)
    
    # Debug
    df_debug = pd.read_csv(debug_path, header=None)
    df_debug['dt'] = pd.to_datetime(df_debug[1], utc=True, errors='coerce')
    df_debug.dropna(subset=['dt'], inplace=True)
    
    print(f"Fills Range: {df_fills['dt'].min()} to {df_fills['dt'].max()}")
    print(f"Debug Range: {df_debug['dt'].min()} to {df_debug['dt'].max()}")

    # Filter ALL Takers
    takers = df_fills[df_fills.get('liquidity') == 'taker']
    print(f"Total Takers: {len(takers)}")
    
    opens = 0
    closes = 0
    unknown = 0
    
    print("\n--- Matching Taker Trades ---")
    for idx, row in takers.iterrows():
        fill_time = row['dt']
        fill_ticker = row['ticker']
        
        # Window: Debug must remain BEFORE Fill.
        # Allow up to 60 seconds BEFORE.
        mask = (df_debug[6] == fill_ticker) & (df_debug['dt'] <= fill_time) & (df_debug['dt'] >= fill_time - pd.Timedelta(seconds=60))
        candidates = df_debug[mask]
        
        if candidates.empty:
            unknown += 1
            continue
            
        last_dec = candidates.iloc[-1]
        
        # Note extraction
        full_row_str = str(last_dec.values)
        
        is_open = "MM_OPEN" in full_row_str
        is_close = "MM_CLOSE" in full_row_str
        
        tag = "UNKNOWN"
        if is_open: tag = "ENTRY (MM_OPEN)"
        if is_close: tag = "EXIT (MM_CLOSE)"
        
        print(f"{fill_time} {fill_ticker}: {tag}")
        
        if is_open: opens += 1
        elif is_close: closes += 1
        else: unknown += 1

    print(f"\nSummary:")
    print(f"  Entries (MM_OPEN): {opens}")
    print(f"  Exits (MM_CLOSE): {closes}")
    print(f"  Unknown: {unknown}")

if __name__ == "__main__":
    main()
