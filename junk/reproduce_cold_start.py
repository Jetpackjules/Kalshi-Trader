import pandas as pd
import numpy as np
from datetime import datetime
import glob
import os

# Mocking the strategy logic
def check_signal(hist, mid, spread):
    # RegimeSwitcher gating
    tight_threshold = np.percentile(hist, 50) if len(hist) > 100 else sum(hist)/len(hist)
    is_tight = spread <= tight_threshold
    
    # InventoryAwareMarketMaker warmup
    if len(hist) < 20:
        return False, "Warmup"
    
    mean_price = np.mean(hist)
    fair_prob = mean_price / 100.0
    
    # Simple edge check (matching backtester)
    edge_yes = fair_prob - (mid / 100.0)
    if edge_yes > 0.01: # 1 cent edge
        return True, f"Signal! Edge: {edge_yes:.4f}"
    
    return False, "No Edge"

LOG_DIR = r"live_trading_system\vm_logs\market_logs"
files = sorted(glob.glob(os.path.join(LOG_DIR, "market_data_KXHIGHNY-25DEC24.csv")))
df = pd.read_csv(files[0])
df['datetime'] = pd.to_datetime(df['timestamp'])

# Filter for 5 AM to 6 AM
df_5am = df[(df['datetime'].dt.hour == 5)]

tickers = df_5am['market_ticker'].unique()

print(f"Analyzing 5 AM period on Dec 24th for {len(tickers)} tickers...")

for t in tickers:
    group = df_5am[df_5am['market_ticker'] == t]
    if len(group) == 0: continue
    
    # Simulating Cold Start (No history from previous days)
    cold_hist = []
    cold_signals = 0
    
    # Simulating Hot Start (Assume 500 ticks of history from previous days)
    # For simplicity, we'll just use the first 20 ticks of the day as "pre-loaded" history
    hot_hist = list(group['best_yes_bid'].iloc[:20]) # Mocking some history
    hot_signals = 0
    
    for i, row in group.iterrows():
        mid = (row['implied_yes_ask'] + row['best_yes_bid']) / 2.0
        spread = row['implied_yes_ask'] - row['best_yes_bid']
        
        # Cold Start
        cold_hist.append(mid)
        sig, reason = check_signal(cold_hist, mid, spread)
        if sig: cold_signals += 1
        
        # Hot Start (Already has history)
        hot_hist.append(mid)
        sig, reason = check_signal(hot_hist, mid, spread)
        if sig: hot_signals += 1
        
    if hot_signals > 0 or cold_signals > 0:
        print(f"Ticker: {t}")
        print(f"  Ticks available: {len(group)}")
        print(f"  Cold Start Signals: {cold_signals}")
        print(f"  Hot Start Signals: {hot_signals}")
