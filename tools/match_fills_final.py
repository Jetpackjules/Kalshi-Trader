
import pandas as pd
import datetime
import os

fills_path = "vm_logs/unified_engine_out/fills.csv"
debug_path = "vm_logs/unified_engine_out/trade_debug.csv"

def main():
    print("--- Final Taker Analysis ---")
    if not os.path.exists(fills_path) or not os.path.exists(debug_path):
        print("Missing logs.")
        return

    # Load Fills
    df_fills = pd.read_csv(fills_path, header=None)
    df_fills.rename(columns={0: 'time', 1: 'ticker', 2: 'side', 3: 'price', 4: 'qty', 5: 'liquidity'}, inplace=True)
    df_fills['dt'] = pd.to_datetime(df_fills['time'], utc=True)
    df_fills['ticker'] = df_fills['ticker'].astype(str).str.strip()
    
    # Load Debug
    df_debug = pd.read_csv(debug_path, header=None)
    # Col 1 is timestamp. It is Naive. Assume UTC.
    df_debug['dt'] = pd.to_datetime(df_debug[1])
    if df_debug['dt'].dt.tz is None:
        df_debug['dt'] = df_debug['dt'].dt.tz_localize('UTC')
    
    # Analyze Takers
    takers = df_fills[df_fills.get('liquidity') == 'taker']
    print(f"Analyzing {len(takers)} Taker Trades...")
    
    entries = 0
    exits = 0
    unknown = 0
    
    for idx, row in takers.iterrows():
        fill_time = row['dt']
        ticker = row['ticker']
        
        # Look for debug log closely preceding the fill (0 to 60s before)
        # Note: Debug time 'log_ts' is when decision was made. Fill is slightly later.
        
        mask = (df_debug[6] == ticker) & \
               (df_debug['dt'] <= fill_time) & \
               (df_debug['dt'] >= fill_time - pd.Timedelta(seconds=60))
               
        candidates = df_debug[mask]
        
        if candidates.empty:
            unknown += 1
            # print(f"  {fill_time.time()} {ticker}: UNKNOWN (No debug log)")
            continue
            
        # Take the LATEST decision before fill
        decision = candidates.iloc[-1]
        
        # Parse decision type from the LAST column
        # Row might look like: ..., "MM_CLOSE(ge=...)"
        raw_note = str(decision.values[-1])
        
        tag = "UNKNOWN"
        if "MM_OPEN" in raw_note:
            tag = "MM_OPEN"
            entries += 1
        elif "MM_CLOSE" in raw_note:
            tag = "MM_CLOSE"
            exits += 1
        else:
            unknown += 1
            
        print(f"  {fill_time.time()} {ticker}: {tag} | Note: {raw_note[:40]}...")

    print(f"\nFinal Taker Breakdown:")
    print(f"  Entries (MM_OPEN): {entries}")
    print(f"  Exits   (MM_CLOSE): {exits}")
    print(f"  Unknown: {unknown}")
    
    if entries > exits:
        print("\nCONCLUSION: We are AGGRESSIVELY ENTERING as Taker. (BAD)")
    else:
        print("\nCONCLUSION: We are mostly exiting as Taker. (Check Exit edge)")

if __name__ == "__main__":
    main()
