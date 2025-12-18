import pandas as pd
import sys
import os

def shrink_log(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    print(f"Shrinking {filepath}...")
    try:
        df = pd.read_csv(filepath)
        original_rows = len(df)
        
        # 1. Remove Exact Duplicates
        df = df.drop_duplicates()
        deduped_rows = len(df)
        
        # 2. Remove Content Duplicates (Consecutive rows with same prices)
        # We need to sort by timestamp to be sure, though logs should be sorted.
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp')
            
        # Group by ticker to compare consecutive rows per ticker
        # We want to keep a row IF it is the first row OR if it differs from the previous row
        # Columns to check for change: best_yes_bid, best_no_bid
        # (Implied asks are derived, so we don't strictly need to check them if bids match)
        
        # We will iterate to check both price change AND time elapsed
        rows_to_keep = []
        last_kept_ts = None
        
        # Convert timestamp to datetime for comparison
        df['dt'] = pd.to_datetime(df['timestamp'], format='mixed')
        
        for ticker, group in df.groupby('market_ticker'):
            group_last_kept_ts = None
            
            for idx, row in group.iterrows():
                keep = False
                
                # 1. Always keep first row of the group
                if group_last_kept_ts is None:
                    keep = True
                else:
                    # 2. Check Price Change
                    # Compare with PREVIOUS row in the group (not necessarily last kept, 
                    # but we want to capture ANY change from the stream)
                    # Actually, we should compare with the LAST KEPT state to be safe?
                    # No, if we skipped rows, we compare with the last kept row to see if state drifted?
                    # Let's stick to: If this row differs from the previous raw row, it's a change event.
                    # But if we skipped intermediate rows, we effectively compare with the last kept.
                    
                    # Let's simplify: Keep if price != last_kept_price OR time > last_kept_time + 60s
                    
                    last_kept_row = df.loc[rows_to_keep[-1]]
                    
                    price_changed = (row['best_yes_bid'] != last_kept_row['best_yes_bid']) or \
                                    (row['best_no_bid'] != last_kept_row['best_no_bid'])
                                    
                    time_elapsed = (row['dt'] - group_last_kept_ts).total_seconds() > 60
                    
                    if price_changed or time_elapsed:
                        keep = True
                        
                if keep:
                    rows_to_keep.append(idx)
                    group_last_kept_ts = row['dt']
        
        # Apply mask
        shrunk_df = df.loc[rows_to_keep].drop(columns=['dt'])
        final_rows = len(shrunk_df)
        
        # Save
        new_filename = filepath.replace(".csv", "_shrunk.csv")
        shrunk_df.to_csv(new_filename, index=False)
        
        print(f"Original: {original_rows} rows")
        print(f"Final:    {final_rows} rows")
        print(f"Reduced by: {original_rows - final_rows} rows ({1 - final_rows/original_rows:.1%})")
        print(f"Saved to: {new_filename}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Support wildcards? Shell handles it usually.
        for arg in sys.argv[1:]:
            shrink_log(arg)
    else:
        print("Usage: python shrink_logs.py <csv_file1> [csv_file2 ...]")
