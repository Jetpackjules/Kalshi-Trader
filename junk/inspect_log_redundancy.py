import pandas as pd

LOG_FILE = r"live_trading_system/vm_logs/market_logs/market_data_KXHIGHNY-25DEC31.csv"
TARGET_TICKER = "KXHIGHNY-25DEC31-B33.5"
START_TIME = "2025-12-30 23:40:00"
END_TIME = "2025-12-30 23:46:00"

def inspect_redundancy():
    print(f"Inspecting {LOG_FILE}...")
    try:
        df = pd.read_csv(LOG_FILE, parse_dates=['timestamp'])
        
        # Filter by Ticker
        df = df[df['market_ticker'] == TARGET_TICKER]
        
        # Filter by Time
        mask = (df['timestamp'] >= START_TIME) & (df['timestamp'] <= END_TIME)
        df_subset = df[mask].copy()
        
        if df_subset.empty:
            print("No data found for this ticker in this time range.")
            return

        print(f"\nFound {len(df_subset)} rows. Showing first 20:")
        print(f"{'Timestamp':<25} | {'YesBid':<6} | {'NoBid':<6} | {'Diff?'}")
        print("-" * 80)
        
        prev_row = None
        for idx, row in df_subset.iterrows():
            ts = row['timestamp']
            y_bid = row['best_yes_bid']
            n_bid = row['best_no_bid']
            
            diff = ""
            if prev_row is not None:
                changes = []
                if y_bid != prev_row['best_yes_bid']: changes.append(f"YesBid({prev_row['best_yes_bid']}->{y_bid})")
                if n_bid != prev_row['best_no_bid']: changes.append(f"NoBid({prev_row['best_no_bid']}->{n_bid})")
                
                if not changes:
                    diff = "NO PRICE CHANGE (Likely Qty Change)"
                else:
                    diff = ", ".join(changes)
            
            print(f"{str(ts):<25} | {y_bid:<6} | {n_bid:<6} | {diff}")
            prev_row = row

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_redundancy()
