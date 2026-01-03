import pandas as pd
import os

CSV_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\market_data.csv"

def clean_csv():
    print(f"Cleaning {CSV_FILE}...")
    try:
        # Read CSV
        df = pd.read_csv(CSV_FILE, on_bad_lines='skip')
        
        # Filter out bad prices
        # Valid prices for "no_ask" or "candle" should be between 0 and 100.
        # We saw -5900, so we filter out anything < 0.
        # We also filter out anything > 100 just in case.
        
        original_count = len(df)
        
        # Convert price to numeric, coercing errors to NaN
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        
        # Drop NaNs in price
        df = df.dropna(subset=['price'])
        
        # Filter
        df_clean = df[(df['price'] >= 0) & (df['price'] <= 100)]
        
        cleaned_count = len(df_clean)
        removed_count = original_count - cleaned_count
        
        if removed_count > 0:
            print(f"Removing {removed_count} bad rows (Prices < 0 or > 100)...")
            df_clean.to_csv(CSV_FILE, index=False)
            print("CSV cleaned successfully.")
        else:
            print("No bad rows found.")
            
    except Exception as e:
        print(f"Error cleaning CSV: {e}")

if __name__ == "__main__":
    clean_csv()
