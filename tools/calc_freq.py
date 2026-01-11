import pandas as pd
import sys

def main():
    try:
        # Use engine='python' and on_bad_lines='skip' to handle the mixed column count
        # Or just read only the first column (timestamp)
        df = pd.read_csv(r"vm_logs\market_logs\market_data_KXHIGHNY-26JAN09.csv", usecols=[0], names=['timestamp'], header=0)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        # Filter for recent logs (last 20 minutes)
        # Assuming file is sorted, just take tail
        recent_df = df.tail(5000) 
        
        recent_df['diff'] = recent_df['timestamp'].diff().dt.total_seconds()
        
        print(f"--- Recent Analysis (Last {len(recent_df)} rows) ---")
        print(f"Last timestamp: {recent_df['timestamp'].max()}")
        
        large_gaps = recent_df[recent_df['diff'] > 10]
        if not large_gaps.empty:
            print(f"\nFound {len(large_gaps)} gaps > 10s:")
            print(large_gaps[['timestamp', 'diff']].tail(10))
        else:
            print("\nNo gaps > 10s found in recent logs.")
            
        print(f"\nRecent Average interval: {recent_df['diff'].mean():.2f} seconds")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
