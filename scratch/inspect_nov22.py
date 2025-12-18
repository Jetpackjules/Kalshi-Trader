from fetch_history import get_full_history
from fetch_nws import get_nws_history
from datetime import datetime, timezone, timedelta
import pandas as pd

def inspect_nov22():
    ticker = "KXHIGHNY-25NOV22-B51.5"
    print(f"Inspecting {ticker}...")
    
    # Fetch Market History
    history = get_full_history(ticker)
    hist_df = pd.DataFrame(history)
    hist_df['time'] = pd.to_datetime(hist_df['end_period_ts'], unit='s', utc=True).dt.tz_convert('US/Eastern')
    hist_df = hist_df.sort_values('time')
    
    # Filter for Nov 22 14:00 ET
    target_time = pd.Timestamp("2025-11-22 14:00:00", tz='US/Eastern')
    window = hist_df[
        (hist_df['time'] >= target_time - timedelta(hours=2)) & 
        (hist_df['time'] <= target_time + timedelta(hours=2))
    ]
    
    print("\nMarket History around 2pm ET:")
    # print(window[['time', 'price', 'yes_bid', 'yes_ask', 'volume']].to_string())
    
    for _, row in window.iterrows():
        print(f"Time: {row['time']}")
        print(f"Price: {row['price']}")
        print(f"Bid: {row.get('yes_bid')} | Ask: {row.get('yes_ask')}")
        print(f"Volume: {row.get('volume')}")
        print("-" * 20)
    
    # Fetch NWS for Nov 22
    start_dt = datetime(2025, 11, 22, 12, 0, tzinfo=timezone.utc)
    end_dt = datetime(2025, 11, 23, 0, 0, tzinfo=timezone.utc)
    nws_df = get_nws_history(start_dt, end_dt)
    nws_df['timestamp'] = pd.to_datetime(nws_df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    nws_df = nws_df.sort_values('timestamp')
    nws_df['cum_max'] = nws_df['temp_f'].expanding().max()
    
    print("\nNWS Data around 2pm ET:")
    print(nws_df[
        (nws_df['timestamp'] >= target_time - timedelta(hours=2)) & 
        (nws_df['timestamp'] <= target_time + timedelta(hours=2))
    ][['timestamp', 'temp_f', 'cum_max']].to_string())

if __name__ == "__main__":
    inspect_nov22()
