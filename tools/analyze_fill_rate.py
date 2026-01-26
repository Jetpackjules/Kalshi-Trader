import pandas as pd
from datetime import datetime, timedelta

def analyze_fill_rate():
    # 1. Load Data
    print("Loading data...")
    try:
        # Kalshi Fills (Ground Truth)
        k_df = pd.read_csv('activity (manually saved)/Kalshi-Recent-Activity-Trade today.csv')
        k_df['dt'] = pd.to_datetime(k_df['Traded_Time'], format='mixed')
        
        # Bot Orders (Intent)
        b_df = pd.read_csv('vm_logs/unified_engine_out/trades.csv')
        b_df['dt'] = pd.to_datetime(b_df['time'])
    except Exception as e:
        print(f"Error loading files: {e}")
        return

    # 2. Filter Time Range (Overlap)
    # Kalshi data is PST (UTC-8), Bot data is UTC (or local?)
    # Based on previous analysis:
    # Kalshi: 09:28 AM - 12:17 PM PST
    # Bot:    09:18 AM - 12:27 PM PST (approx)
    
    start_time = k_df['dt'].min()
    end_time = k_df['dt'].max()
    duration_minutes = (end_time - start_time).total_seconds() / 60.0
    
    print(f"\nTime Range: {start_time} to {end_time}")
    print(f"Duration: {duration_minutes:.1f} minutes")
    
    # 3. Calculate Metrics
    total_fills = len(k_df)
    total_volume = k_df['Amount_In_Dollars'].sum() # Assuming column exists
    
    fills_per_minute = total_fills / duration_minutes
    
    print(f"\n--- Fill Metrics ---")
    print(f"Total Fills:      {total_fills}")
    print(f"Fills per Minute: {fills_per_minute:.2f}")
    
    # 4. Estimate Probability
    # Assumption: We maintain ~10 active orders (5 levels * 2 sides)
    active_orders = 10
    prob_per_minute = fills_per_minute / active_orders
    
    print(f"\n--- Probability Model ---")
    print(f"Assumed Active Orders: {active_orders}")
    print(f"Fill Prob per Order/Min: {prob_per_minute:.2f} ({(prob_per_minute*100):.1f}%)")
    
    # 5. Suggest SimAdapter Config
    print(f"\n--- Suggested SimAdapter Config ---")
    print(f"fill_prob_per_min = {prob_per_minute:.4f}")

if __name__ == "__main__":
    analyze_fill_rate()
