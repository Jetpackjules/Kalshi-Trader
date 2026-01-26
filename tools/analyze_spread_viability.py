
import csv
import sys
import glob
import os
import numpy as np
from collections import defaultdict
from datetime import datetime

def analyze_viability(log_dir):
    files = sorted(glob.glob(os.path.join(log_dir, "market_data_*.csv")))
    print(f"Found {len(files)} files to analyze.")
    
    # Metrics per ticker
    ticker_stats = defaultdict(lambda: {
        "spreads": [],
        "trade_count": 0,
        "price_changes": [],
        "min_price": 100,
        "max_price": 0,
        "total_ticks": 0
    })
    
    total_files = len(files)
    for i, file_path in enumerate(files):
        print(f"[{i+1}/{total_files}] Processing {os.path.basename(file_path)}...", end="\r")
        
        last_trade_prices = {}
        
        try:
            with open(file_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ticker = row.get("market_ticker")
                    if not ticker: continue
                    
                    # Parse prices
                    try:
                        yes_bid = float(row.get("best_yes_bid") or 0)
                        yes_ask = float(row.get("implied_yes_ask") or 100)
                        last_trade = float(row.get("last_trade_price") or 0)
                    except ValueError:
                        continue
                        
                    # Calculate spread
                    spread = yes_ask - yes_bid
                    if spread < 0: spread = 0 # Should not happen but safety first
                    if spread > 100: spread = 100
                    
                    stats = ticker_stats[ticker]
                    stats["spreads"].append(spread)
                    stats["total_ticks"] += 1
                    
                    # Track Price Range
                    mid = (yes_bid + yes_ask) / 2
                    if mid < stats["min_price"]: stats["min_price"] = mid
                    if mid > stats["max_price"]: stats["max_price"] = mid
                    
                    # Detect Trades
                    prev_last_trade = last_trade_prices.get(ticker)
                    if prev_last_trade is not None and last_trade != prev_last_trade:
                        stats["trade_count"] += 1
                        stats["price_changes"].append(last_trade - prev_last_trade)
                        
                    last_trade_prices[ticker] = last_trade
                    
        except Exception as e:
            print(f"\nError processing {file_path}: {e}")
            continue

    print("\n" + "="*100)
    print(f"{'Ticker':<25} | {'Avg Spread':<10} | {'Trades':<8} | {'Ticks':<8} | {'Vol/Tick':<8} | {'Range':<10}")
    print("-" * 100)
    
    # Aggregate and sort by trade count
    results = []
    for ticker, stats in ticker_stats.items():
        if not stats["spreads"]: continue
        
        avg_spread = np.mean(stats["spreads"])
        trade_count = stats["trade_count"]
        total_ticks = stats["total_ticks"]
        vol_per_tick = trade_count / total_ticks if total_ticks > 0 else 0
        price_range = f"{stats['min_price']:.0f}-{stats['max_price']:.0f}"
        
        results.append((ticker, avg_spread, trade_count, total_ticks, vol_per_tick, price_range))
        
    # Sort by Trade Count (descending)
    results.sort(key=lambda x: x[2], reverse=True)
    
    for r in results:
        print(f"{r[0]:<25} | {r[1]:<10.2f} | {r[2]:<8} | {r[3]:<8} | {r[4]:<8.4f} | {r[5]:<10}")

    # Global Stats
    all_spreads = [s for stats in ticker_stats.values() for s in stats["spreads"]]
    avg_global_spread = np.mean(all_spreads) if all_spreads else 0
    total_trades = sum(r[2] for r in results)
    
    print("="*100)
    print(f"Global Average Spread: {avg_global_spread:.2f} cents")
    print(f"Total Detected Trades: {total_trades}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_spread_viability.py <log_dir>")
        sys.exit(1)
    analyze_viability(sys.argv[1])
