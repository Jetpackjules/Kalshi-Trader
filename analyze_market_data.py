import pandas as pd
import os

# Load Dec 17 data
file_path = r"c:/Users/jetpa/OneDrive - UW/Google_Grav_Onedrive/kalshi_weather_data/live_trading_system/vm_logs/market_logs/market_data_KXHIGHNY-25DEC17.csv"
df = pd.read_csv(file_path, on_bad_lines='skip')

with open('analysis_output_utf8.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total Rows: {len(df)}\n")
    unique_tickers = df['market_ticker'].unique()
    f.write(f"Unique Tickers: {len(unique_tickers)}\n")
    f.write(f"Tickers: {unique_tickers}\n")

    # Check for valid candidates (Price 50-70)
    df['no_price'] = 100 - df['implied_yes_ask']
    valid_rows = df[(df['no_price'] > 50) & (df['no_price'] < 70)]

    f.write(f"Rows with Valid Price (50-70): {len(valid_rows)}\n")
    if not valid_rows.empty:
        f.write("Sample Valid Rows:\n")
        f.write(valid_rows[['timestamp', 'market_ticker', 'no_price']].head(10).to_string() + "\n")
        
        # Check concurrent valid markets
        # Round to nearest second to see if they align
        valid_rows['timestamp_rounded'] = pd.to_datetime(valid_rows['timestamp']).dt.round('1s')
        valid_counts = valid_rows.groupby('timestamp_rounded')['market_ticker'].nunique()
        f.write("\nConcurrent Valid Markets (Rounded 1s) (Distribution):\n")
        f.write(valid_counts.value_counts().sort_index().to_string() + "\n")
    else:
        f.write("No valid rows found.\n")
