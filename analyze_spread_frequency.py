
import pandas as pd
import glob
import os

DATA_DIR = "vm_logs/market_logs"

def analyze_spreads():
    # Filter for Feb 2026 files only
    files = glob.glob(os.path.join(DATA_DIR, "market_data_KXHIGHNY-26FEB*.csv"))
    if not files:
        print(f"No data files found in {DATA_DIR}")
        return

    print(f"Analyzing {len(files)} market data files...")
    
    all_spreads = []
    
    for f in files:
        try:
            # Read only relevant columns to save memory
            df = pd.read_csv(f, usecols=["best_yes_bid", "implied_yes_ask"])
            
            # Filter for valid quotes (non-zero)
            valid = df[(df["best_yes_bid"] > 0) & (df["implied_yes_ask"] > 0)].copy()
            
            if not valid.empty:
                # Calculate Spread = Ask - Bid
                valid["spread"] = valid["implied_yes_ask"] - valid["best_yes_bid"]
                all_spreads.extend(valid["spread"].tolist())
                
        except Exception as e:
            print(f"Error reading {f}: {e}")
            continue

    if not all_spreads:
        print("No valid spread data found.")
        return

    # Create frequency distribution
    s_series = pd.Series(all_spreads)
    counts = s_series.value_counts().sort_index()
    total = len(s_series)
    
    print("\nSpread Frequency Analysis:")
    print("-" * 40)
    print(f"{'Spread (cents)':<15} | {'Count':<10} | {'Frequency (%)':<10}")
    print("-" * 40)
    
    print(f"Total Samples: {total}")
    
    print("\nCumulative Frequency (Spread >= X):")
    print("-" * 40)
    for threshold in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20]:
        # Count spreads >= threshold
        count = s_series[s_series >= threshold].count()
        pct = (count / total) * 100
        print(f"Spread >= {threshold:2d}c : {pct:>6.2f}%")
    print("-" * 40)

if __name__ == "__main__":
    analyze_spreads()
