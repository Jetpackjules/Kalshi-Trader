import pandas as pd

# Load a sample log file
file_path = r"c:/Users/jetpa/OneDrive - UW/Google_Grav_Onedrive/kalshi_weather_data/live_trading_system/vm_logs/market_logs/market_data_KXHIGHNY-25DEC17.csv"
df = pd.read_csv(file_path, on_bad_lines='skip')

# Pre-processing
df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
total_rows = len(df)

# Unrounded unique timestamps
unique_unrounded = df['timestamp'].nunique()

# Rounded unique timestamps
df['timestamp_rounded'] = df['timestamp'].dt.round('1s')
unique_rounded = df['timestamp_rounded'].nunique()

# Check for "Fleeting" Prices
# Group by rounded timestamp and see if we have multiple DIFFERENT prices for the SAME ticker in the same second
df['yes_ask'] = df['implied_yes_ask']
grouped = df.groupby(['timestamp_rounded', 'market_ticker'])['yes_ask'].nunique()
conflicts = grouped[grouped > 1]

with open('loss_report_utf8.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total Rows: {total_rows}\n")
    f.write(f"Unique Timestamps (Unrounded): {unique_unrounded}\n")
    f.write(f"Unique Timestamps (Rounded 1s): {unique_rounded}\n")
    f.write(f"Data Loss: {100 - (unique_rounded / unique_unrounded * 100):.1f}% of time-points merged.\n")

    f.write(f"\nConflicting Prices within 1s: {len(conflicts)}\n")
    if not conflicts.empty:
        f.write("Examples of price changes lost/merged within 1s:\n")
        f.write(conflicts.head().to_string() + "\n")
