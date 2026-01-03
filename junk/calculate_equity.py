import pandas as pd

# Load trades
df = pd.read_csv(r'c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\trades.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Filter for Dec 23
dec23_trades = df[df['timestamp'].dt.date == pd.to_datetime('2025-12-23').date()]

# Calculate PnL
# Cost = price * qty / 100 + fee
# We don't have settlement info here easily, but we can approximate or just look at the realized PnL if available.
# Wait, the backtester needs *Available Cash* and *Portfolio Value*.
# If we just want to match the backtester, we should start the backtester on Dec 24 with the *Live Bot's* equity at that time.

# Let's assume the user wants to run the backtester *for Dec 24* to see if it matches the *Dec 24 trades*.
# So we need the equity at the *beginning* of Dec 24.

# Calculate cost of Dec 23 trades
dec23_cost = (dec23_trades['price'] * dec23_trades['qty'] / 100.0).sum() + dec23_trades['fee'].sum()

print(f"Dec 23 Trades Count: {len(dec23_trades)}")
print(f"Dec 23 Total Cost: ${dec23_cost:.2f}")

# We need to know if any Dec 23 trades *settled* on Dec 23 to calculate equity.
# KXHIGHNY-25DEC23 markets settle on Dec 24 (or late Dec 23).
# If they settled, we need the payout.

# Let's look at the tickers.
print("Dec 23 Tickers:")
print(dec23_trades['ticker'].unique())
