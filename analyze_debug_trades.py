import pandas as pd

# Load trades
df = pd.read_csv("debug_trades.csv")
df.columns = df.columns.str.strip()
print(f"Columns: {df.columns.tolist()}")

# Filter for Safe Baseline (Winner)
# Handle potential NaNs in strategy column
baseline_trades = df[df['strategy'].fillna('').str.contains("Safe Baseline")]

print(f"Total Baseline Trades: {len(baseline_trades)}")

if baseline_trades.empty:
    print("No baseline trades found! Check strategy names:")
    print(df['strategy'].unique())
else:
    print("\n--- Trade Analysis ---")
    try:
        print(baseline_trades[['time', 'ticker', 'action', 'price', 'pnl']].head(20))
    except KeyError as e:
        print(f"KeyError accessing columns: {e}")
        print(f"Available columns: {baseline_trades.columns.tolist()}")

    # Check Price Distribution
    print("\n--- Price Stats ---")
    if 'price' in baseline_trades.columns:
        print(baseline_trades['price'].describe())
    else:
        print("'price' column missing from baseline_trades")

# Check if we bought multiple times in the same second
if not baseline_trades.empty:
    baseline_trades = baseline_trades.copy()
    baseline_trades['timestamp'] = pd.to_datetime(baseline_trades['time'])
    baseline_trades['second'] = baseline_trades['timestamp'].dt.round('1s')

    dupes = baseline_trades.groupby('second').size()
    print(f"\nTrades per second (Max): {dupes.max()}")
    if dupes.max() > 1:
        print("Multiple trades in same second detected!")
        print(dupes[dupes > 1])
else:
    print("No baseline trades found.")
