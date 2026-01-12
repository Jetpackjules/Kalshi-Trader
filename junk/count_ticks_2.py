import pandas as pd
from datetime import datetime

file_path = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\vm_logs\market_logs\market_data_KXHIGHNY-26JAN09.csv"
target_ticker = "KXHIGHNY-26JAN09-B49.5"

print(f"Reading {file_path}...")
try:
    # Handle variable column counts
    col_names = ["timestamp", "market_ticker", "best_yes_bid", "best_no_bid", "implied_no_ask", "implied_yes_ask", "last_trade_price"]
    df = pd.read_csv(file_path, names=col_names, header=None, on_bad_lines='skip')
    
    # Drop header if present
    if len(df) > 0 and str(df.iloc[0]['timestamp']).strip() == 'timestamp':
        df = df.iloc[1:]
        
    df['datetime'] = pd.to_datetime(df['timestamp'], format='mixed', dayfirst=True)
    
    # Filter for ticker
    df_ticker = df[df['market_ticker'] == target_ticker]
    print(f"Total ticks for {target_ticker}: {len(df_ticker)}")
    
    # Filter for time > 06:00
    cutoff = datetime(2026, 1, 9, 6, 0, 0)
    df_after = df_ticker[df_ticker['datetime'] > cutoff]
    print(f"Ticks after {cutoff}: {len(df_after)}")
    
    if not df_after.empty:
        print("First 5 ticks after cutoff:")
        print(df_after.head())
        print("Last 5 ticks after cutoff:")
        print(df_after.tail())

except Exception as e:
    print(f"Error: {e}")
