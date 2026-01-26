import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import glob
import os

def analyze_fill_vs_spread():
    print("--- Analyzing Fill Probability vs Spread ---")

    # 1. Load Trade Data (Fills)
    print("Loading Trade Data...")
    try:
        trades_df = pd.read_csv('activity (manually saved)/Kalshi-Recent-Activity-Trade today.csv')
        # Parse UTC timestamp and convert to Local (PST = UTC-8)
        trades_df['dt_utc'] = pd.to_datetime(trades_df['Original_Date'], format='mixed')
        # Convert to naive local time
        if trades_df['dt_utc'].dt.tz is not None:
            trades_df['dt_utc'] = trades_df['dt_utc'].dt.tz_convert(None)
        trades_df['dt_local'] = trades_df['dt_utc'] - timedelta(hours=8)
        print(f"Loaded {len(trades_df)} trades.")
    except Exception as e:
        print(f"Error loading trades: {e}")
        return

    # 2. Load Market Data
    print("Loading Market Data...")
    market_file = "vm_logs/market_logs/market_data_KXHIGHNY-26JAN21.csv"
    if not os.path.exists(market_file):
        print(f"Market file not found: {market_file}")
        return

    try:
        # Columns: timestamp,market_ticker,best_yes_bid,best_no_bid,implied_no_ask,implied_yes_ask,last_trade_price
        # Note: header might be missing or present. Based on `head`, it has a header.
        mkt_df = pd.read_csv(market_file)
        mkt_df['dt'] = pd.to_datetime(mkt_df['timestamp'])
        print(f"Loaded {len(mkt_df)} market ticks.")
    except Exception as e:
        print(f"Error loading market data: {e}")
        return

    # 3. Filter Market Data to Trade Session
    # Use the range of trades + buffer
    start_time = trades_df['dt_local'].min() - timedelta(minutes=10)
    end_time = trades_df['dt_local'].max() + timedelta(minutes=10)
    
    print(f"Filtering Market Data: {start_time} to {end_time}")
    mkt_df = mkt_df[(mkt_df['dt'] >= start_time) & (mkt_df['dt'] <= end_time)].copy()
    
    if len(mkt_df) == 0:
        print("No market data in the trade window!")
        return

    # 4. Calculate Spread for each tick
    # Spread = Ask - Bid
    # We need Best Yes Ask.
    # The file has `implied_yes_ask`.
    # Spread = implied_yes_ask - best_yes_bid
    
    # Clean data
    mkt_df['yes_bid'] = pd.to_numeric(mkt_df['best_yes_bid'], errors='coerce')
    mkt_df['yes_ask'] = pd.to_numeric(mkt_df['implied_yes_ask'], errors='coerce')
    mkt_df.dropna(subset=['yes_bid', 'yes_ask'], inplace=True)
    
    mkt_df['spread'] = mkt_df['yes_ask'] - mkt_df['yes_bid']
    mkt_df = mkt_df[mkt_df['spread'] > 0] # Filter invalid spreads

    # 5. Resample to 1-second intervals per Ticker to calculate "Time at Spread"
    # We want to know: For how many seconds was Ticker X at Spread S?
    
    print("Resampling Market Data...")
    tickers = mkt_df['market_ticker'].unique()
    
    spread_counts = {} # {spread: seconds}
    
    # We can iterate by ticker
    for ticker in tickers:
        tdf = mkt_df[mkt_df['market_ticker'] == ticker].sort_values('dt')
        if len(tdf) < 2: continue
        
        # Resample to 1s
        tdf = tdf.set_index('dt')
        # Resample and forward fill
        # Limit to the session range
        tdf_resampled = tdf.resample('1s').last().ffill()
        
        # Count seconds at each spread
        counts = tdf_resampled['spread'].value_counts()
        for spread, count in counts.items():
            spread = int(spread)
            spread_counts[spread] = spread_counts.get(spread, 0) + count

    # 6. Match Fills to Spreads
    print("Matching Fills to Spreads...")
    fill_spreads = []
    
    # Sort market data for `asof` merge
    mkt_df.sort_values('dt', inplace=True)
    
    for idx, row in trades_df.iterrows():
        trade_time = row['dt_local']
        ticker = row['Market_Ticker']
        
        # Find market state for this ticker at/before trade_time
        # We can use merge_asof if we separate by ticker, or just simple filter
        # Since N is small (trades), simple filter is fine.
        
        # Get ticks for this ticker before trade_time
        mask = (mkt_df['market_ticker'] == ticker) & (mkt_df['dt'] <= trade_time)
        # Get the last one
        try:
            last_tick = mkt_df[mask].iloc[-1]
            # Check if it's stale (e.g. > 1 min old)
            if (trade_time - last_tick['dt']).total_seconds() > 60:
                # print(f"Warning: Stale tick for {ticker} at {trade_time}")
                pass
            
            spread = int(last_tick['spread'])
            fill_spreads.append(spread)
        except IndexError:
            # print(f"No tick found for {ticker} before {trade_time}")
            pass

    fill_counts = {}
    for s in fill_spreads:
        fill_counts[s] = fill_counts.get(s, 0) + 1
        
    # 7. Calculate Probabilities
    print("\n--- Results: Fill Probability vs Spread ---")
    print(f"{'Spread':<8} | {'Time (min)':<12} | {'Fills':<8} | {'Fills/Min':<10} | {'Prob/Order/Min':<15}")
    print("-" * 65)
    
    # Assuming we have orders on BOTH sides?
    # Or just one side?
    # If Spread=1, we are likely at Bid or Ask.
    # If Spread=10, we are at Bid (Ask is +10).
    # The "Time" is "Time the market existed at this spread".
    # If we are a Market Maker, we likely have 1 order (or 2) in the market.
    # Let's assume 2 orders (Bid and Ask) active per ticker.
    # So "Order-Minutes" = Time(min) * 2.
    
    sorted_spreads = sorted(spread_counts.keys())
    for s in sorted_spreads:
        seconds = spread_counts[s]
        minutes = seconds / 60.0
        fills = fill_counts.get(s, 0)
        
        if minutes < 1.0: continue # Skip insignificant data
        
        fills_per_min = fills / minutes
        
        # Prob per Order per Min
        # Assumption: We have 2 orders active (Bid + Ask)
        prob = fills_per_min / 2.0
        
        print(f"{s:<8} | {minutes:<12.1f} | {fills:<8} | {fills_per_min:<10.2f} | {prob:<15.4f}")

if __name__ == "__main__":
    analyze_fill_vs_spread()
