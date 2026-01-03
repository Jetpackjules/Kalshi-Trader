import pandas as pd
import os

TRADES_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\trades.csv"

def inspect():
    if not os.path.exists(TRADES_FILE):
        print("Trades file not found.")
        return

    df = pd.read_csv(TRADES_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    # Filter for Dec 24
    dec24 = df[df['timestamp'].dt.date == pd.to_datetime('2025-12-24').date()]
    
    with open('dec24_trades_dump.txt', 'w') as f:
        f.write(f"Found {len(dec24)} trades on Dec 24.\n")
        if not dec24.empty:
            f.write(dec24.head(20).to_string())
            
        dec23 = df[df['timestamp'].dt.date == pd.to_datetime('2025-12-23').date()]
        f.write(f"\n\nFound {len(dec23)} trades on Dec 23.\n")
        if not dec23.empty:
            f.write(dec23.tail(10).to_string())
            
    print("Dumped to dec24_trades_dump.txt")

if __name__ == "__main__":
    inspect()
