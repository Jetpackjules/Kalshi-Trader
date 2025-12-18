import pandas as pd
from datetime import datetime, timedelta, timezone
import sys
import os

# Mock Streamlit for debug
class MockSt:
    def write(self, msg):
        print(msg)
    def progress(self, val):
        pass
    def empty(self):
        return self
    def text(self, msg):
        print(msg)

st = MockSt()

from fetch_orderbook import get_markets_by_date
from fetch_history import get_full_history
from fetch_nws import get_nws_history

def debug_safe_strategy():
    print("--- DEBUGGING SAFE STRATEGY (NOV 22) ---")
    date_str = "NOV22"
    strategy_name = "Safe (NWS Arbitrage)"
    initial_capital = 100
    cash = initial_capital
    
    # 1. Fetch Markets
    markets = get_markets_by_date(date_str, status="open,closed,settled")
    print(f"Found {len(markets)} markets for {date_str}")
    
    # NWS Data
    start_dt = datetime(2025, 11, 22, 14, 0, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(hours=24)
    nws_df = get_nws_history(start_dt, end_dt)
    nws_df['timestamp'] = pd.to_datetime(nws_df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    nws_df = nws_df.sort_values('timestamp')
    nws_df['cum_max'] = nws_df['temp_f'].expanding().max()
    
    print(f"NWS Data: {len(nws_df)} rows")
    
    for market in markets:
        ticker = market['ticker']
        if "B51.5" not in ticker: continue # Focus on the problematic ticker
        
        print(f"\nAnalyzing {ticker}...")
        strike = float(ticker.split("-B")[1])
        
        history = get_full_history(ticker)
        hist_df = pd.DataFrame(history)
        hist_df['time'] = pd.to_datetime(hist_df['end_period_ts'], unit='s', utc=True).dt.tz_convert('US/Eastern')
        hist_df = hist_df.sort_values('time')
        
        print(f"History: {len(hist_df)} rows")
        
        # Check 14:00 row specifically
        target_time = pd.Timestamp("2025-11-22 14:00:00", tz='US/Eastern')
        mask = (hist_df['time'] >= target_time - timedelta(minutes=10)) & (hist_df['time'] <= target_time + timedelta(minutes=10))
        print("Raw History around 14:00:")
        print(f"Columns: {hist_df.columns}")
        # print(hist_df[mask][['time', 'close', 'volume']].to_string())
        print(hist_df[mask].to_string())
        
        # Merge
        merged = pd.merge_asof(hist_df, nws_df, left_on='time', right_on='timestamp', direction='backward', tolerance=pd.Timedelta(hours=2))
        
        print(f"Merged: {len(merged)} rows")
        
        for _, row in merged.iterrows():
            if pd.isna(row['timestamp']): continue
            
            current_time = row['time']
            # Only look at 14:00
            if current_time.hour == 14 and current_time.minute == 0:
                print(f"\n--- Simulation Step at {current_time} ---")
                current_max = row['cum_max']
                price_data = row['price']
                print(f"Price Data Type: {type(price_data)}")
                print(f"Price Data: {price_data}")
                
                if isinstance(price_data, dict):
                    yes_price = price_data.get('close')
                else:
                    yes_price = price_data
                    
                no_price = 100 - yes_price if yes_price is not None else None
                
                print(f"Price (Close): {yes_price}")
                print(f"NO Price: {no_price}")
                print(f"Max: {current_max}, Strike: {strike}")
                
                if current_max >= strike:
                    print("\n--- DETAILED INSPECTION ---")
                    print(f"Time: {current_time}")
                    print(f"NWS Max So Far: {current_max} (Strike: {strike})")
                    print(f"Market Price Data: {price_data}")
                    
                    # Print NWS context
                    print("\nNWS Readings around this time:")
                    context_mask = (nws_df['timestamp'] >= current_time - timedelta(minutes=60)) & (nws_df['timestamp'] <= current_time + timedelta(minutes=60))
                    print(nws_df[context_mask][['timestamp', 'temp_f', 'cum_max']].to_string())
                    
                    # REALITY CHECK
                    if no_price < 98 and no_price >= 10:
                        print(f"BUY SIGNAL: NO Price {no_price} < 98")
                    else:
                        print(f"SKIPPED: Price {no_price} too low (Reality Check)")

if __name__ == "__main__":
    debug_safe_strategy()
