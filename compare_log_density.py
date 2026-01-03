import pandas as pd
from datetime import datetime, timedelta
import os

# Configuration
FILE_OLD = r"live_trading_system/vm_logs/market_logs/market_data_KXHIGHNY-25DEC26.csv"
FILE_NEW = r"live_trading_system/vm_logs/market_logs/market_data_KXHIGHNY-26JAN01.csv"

def count_density(filepath, label):
    print(f"Analyzing {label}: {filepath}")
    if not os.path.exists(filepath):
        print(f"  File not found: {filepath}")
        return None

    try:
        # Read CSV (timestamp is first column)
        df = pd.read_csv(filepath, parse_dates=['timestamp'])
        
        # Filter for 10:00 AM - 11:00 AM (approx current time)
        # We ignore the date part for comparison, just look at time
        df['time_only'] = df['timestamp'].dt.time
        
        start_time = datetime.strptime("10:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("11:00:00", "%H:%M:%S").time()
        
        mask = (df['time_only'] >= start_time) & (df['time_only'] <= end_time)
        df_filtered = df[mask].copy()
        
        if df_filtered.empty:
            print(f"  No data between 10:00 and 11:00 for {label}")
            return 0
            
        # Resample to 5-min intervals (need a dummy date for resampling)
        df_filtered['dummy_dt'] = pd.to_datetime('2000-01-01 ' + df_filtered['time_only'].astype(str))
        resampled = df_filtered.set_index('dummy_dt').resample('5min').size()
        
        avg_count = resampled.mean()
        print(f"  {label} Density (10-11 AM): {avg_count:.1f} lines per 5 min")
        return avg_count

    except Exception as e:
        print(f"  Error analyzing {label}: {e}")
        return None

print("--- Log Density Comparison ---")
density_old = count_density(FILE_OLD, "Historical (Dec 26)")
density_new = count_density(FILE_NEW, "Current (Jan 01)")

if density_old is not None and density_new is not None:
    print("\n--- Result ---")
    print(f"Historical: {density_old:.1f} lines/5min")
    print(f"Current:    {density_new:.1f} lines/5min")
    
    if density_new < density_old * 0.5:
        print("WARNING: Significant drop in log density!")
    else:
        print("Density is comparable.")
