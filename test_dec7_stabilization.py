import pandas as pd
import os
import glob
from datetime import datetime, timedelta

# Define the Strategy Logic exactly as in the backtester
class WaitForStabilizationStrategy:
    def __init__(self): 
        self.name = "Wait for Stabilization"
        
    def on_tick(self, market, current_temp, market_price, current_time):
        # Only trade after 10:30 AM ET (15:30 UTC)
        if current_time.hour < 15 or (current_time.hour == 15 and current_time.minute < 30):
            return "HOLD", "Too Early"
            
        no_price = 100 - market_price
        
        # Logic: 50 < no_price < 70
        if 50 < no_price < 70: 
            return "BUY_NO", f"Valid (Price {no_price})"
            
        if no_price <= 50: return "HOLD", f"Price too low ({no_price} <= 50)"
        if no_price >= 70: return "HOLD", f"Price too high ({no_price} >= 70)"
        
        return "HOLD", "Unknown"

# Load Data for Dec 7th (Log file ending in 25DEC07)
# Note: The log file name usually corresponds to the CONTRACT DATE, not necessarily the trade date.
# The user mentioned "Dec 7, on the graph it shows you buying at 3:30pm on dev 6th".
# So we need the log file that covers Dec 6th trading session.
# That would likely be `market_data_KXHIGHNY-25DEC07.csv` (Contract for Dec 7, trading on Dec 6).
# Let's check the file list.

LOG_DIR = r"C:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
target_file = os.path.join(LOG_DIR, "market_data_KXHIGHNY-25DEC07.csv")

print(f"Analyzing: {target_file}")

if not os.path.exists(target_file):
    print("File not found!")
    exit()

df = pd.read_csv(target_file, on_bad_lines='skip')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.sort_values('timestamp')

strategy = WaitForStabilizationStrategy()

print(f"{'Time (UTC)':<20} | {'Ticker':<25} | {'NO Price':<8} | {'Signal':<10} | {'Reason'}")
print("-" * 100)

# Filter for the relevant time window (Dec 6th afternoon)
# The user mentioned 3:30 PM (15:30). If local time is EST, that's 20:30 UTC.
# Wait, the strategy uses UTC hours in the code: `if current_time.hour < 15`.
# 15:30 UTC is 10:30 AM EST.
# The user said "buying at 3:30pm on dec 6th".
# 3:30 PM EST = 20:30 UTC.
# Let's just print everything after 15:00 UTC to see what happened.

for index, row in df.iterrows():
    timestamp = row['timestamp']
    
    # Filter for Dec 6th (The trading day before Dec 7 contract)
    if timestamp.day != 6: continue
    
    # Only look at afternoon/relevant times
    if timestamp.hour < 15: continue 
    
    ticker = row['market_ticker']
    
    # Calculate NO Price
    # Assuming 'implied_no_ask' is the price we buy at
    no_price = row.get('implied_no_ask')
    if pd.isna(no_price):
        # Try to infer from yes_ask
        yes_ask = row.get('implied_yes_ask')
        if not pd.isna(yes_ask):
            no_price = 100 - yes_ask
        else:
            continue
            
    # Run Strategy
    # We pass 0 as temp since we don't have it, but this strategy doesn't use it.
    signal, reason = strategy.on_tick({}, 0, 100-no_price, timestamp) 
    # Note: on_tick expects MARKET PRICE (YES Price). 
    # So we pass 100 - no_price.
    
    # Print interesting events (Transitions or Buys)
    # We want to see why it DIDN'T buy earlier.
    # So let's print if it's close (e.g. price between 40 and 80)
    
    if 40 < no_price < 80:
        print(f"{timestamp.strftime('%H:%M:%S'):<20} | {ticker:<25} | {no_price:<8.1f} | {signal:<10} | {reason}")

