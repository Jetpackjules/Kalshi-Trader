
import csv
import pandas as pd
import datetime
import os
import glob

# Load fills
fills_path = "vm_logs/unified_engine_out/fills.csv"
market_data_dir = "vm_logs/market_logs"

def load_market_data(ticker):
    base = "-".join(ticker.split("-")[:2])
    pattern = os.path.join(market_data_dir, f"market_data_{base}.csv")
    files = glob.glob(pattern)
    if not files:
        return None
        
    path = files[0]
    try:
        df = pd.read_csv(path)
        # Ensure timestamp parsing
        df['dt'] = pd.to_datetime(df['timestamp'], utc=True)
        # Strip TZ for easier comparison if needed, or keep UTC
        df['dt'] = df['dt'].dt.tz_localize(None)
        return df
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None

def analyze_feb5():
    print("--- Simulating Maker Execution (Corrected) ---")
    if not os.path.exists(fills_path):
        return

    df_fills = pd.read_csv(fills_path, header=None)
    df_fills.rename(columns={0: 'time', 1: 'ticker', 2: 'side', 3: 'price', 4: 'qty', 5: 'liquidity'}, inplace=True)
    
    # Parse fill times as UTC then strip
    df_fills['dt'] = pd.to_datetime(df_fills['time'], utc=True).dt.tz_localize(None)
    
    # Filter for Feb 5th
    feb5_fills = df_fills[df_fills['dt'].dt.date == datetime.date(2026, 2, 5)]
    takers = feb5_fills[feb5_fills.get('liquidity') == 'taker']
    
    maker_success = 0
    maker_fail = 0
    
    market_dfs = {}
    
    print(f"Checking {len(takers)} taker trades...")
    
    for idx, row in takers.iterrows():
        ticker = row['ticker']
        fill_price = row['price'] # Dollars (e.g. 0.77)
        fill_time = row['dt']
        
        base_ticker = "-".join(ticker.split("-")[:2])
        
        if base_ticker not in market_dfs:
            market_dfs[base_ticker] = load_market_data(ticker)
            
        mdf = market_dfs.get(base_ticker)
        if mdf is None or mdf.empty:
            continue
            
        future_data = mdf[mdf['dt'] > fill_time]
        if future_data.empty:
            maker_fail += 1
            continue
            
        # Correct Target Price Calculation:
        # Convert fill (dollars) to cents.
        fill_cents = int(round(fill_price * 100))
        target_price = fill_cents - 1
        
        # 'market_ticker' is the column
        specific_future = future_data[future_data['market_ticker'] == ticker]
        
        # Check 'last_trade_price' (cents)
        matches = specific_future[specific_future['last_trade_price'] <= target_price]
        
        if not matches.empty:
            maker_success += 1
            first_match = matches.iloc[0]
            delay = (first_match['dt'] - fill_time).total_seconds()
            print(f"  Trade {idx}: SUCCESS! Filled at {target_price} (vs {fill_cents}) after {delay:.1f}s")
        else:
            maker_fail += 1
            print(f"  Trade {idx}: Fail. Price ({fill_cents}) never touched {target_price}")

    print(f"\nSimulation Result: {maker_success} Success / {maker_fail} Fail")
    success_rate = (maker_success / (maker_success + maker_fail)) * 100 if (maker_success+maker_fail)>0 else 0
    print(f"Maker Viability Rate: {success_rate:.1f}%")

if __name__ == "__main__":
    analyze_feb5()
