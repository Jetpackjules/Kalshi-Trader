import pandas as pd
import sys

def analyze_duplicates(filepath):
    print(f"Analyzing {filepath}...")
    try:
        df = pd.read_csv(filepath)
        total_rows = len(df)
        print(f"Total Rows: {total_rows}")
        
        # Check for exact duplicates (all columns including timestamp)
        exact_dupes = df.duplicated().sum()
        print(f"Exact Duplicates: {exact_dupes} ({exact_dupes/total_rows:.1%})")
        
        # Check for "Content Duplicates" (Same ticker, same prices, different timestamp)
        # We want to know if the state didn't change but we logged it anyway.
        # Shift the columns to compare with previous row
        # Group by ticker first
        content_dupes = 0
        for ticker, group in df.groupby('market_ticker'):
            # Compare current row with previous row for price columns
            # Columns: best_yes_bid, best_no_bid
            cols = ['best_yes_bid', 'best_no_bid']
            
            # Shift to get previous values
            prev = group[cols].shift(1)
            
            # Check where current == prev
            is_dupe = (group[cols] == prev).all(axis=1)
            # First row is always False (NaN comparison), which is correct (new state)
            content_dupes += is_dupe.sum()
            
        print(f"Redundant Updates (No Price Change): {content_dupes} ({content_dupes/total_rows:.1%})")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_duplicates(sys.argv[1])
    else:
        print("Usage: python analyze_duplicates.py <csv_file>")
