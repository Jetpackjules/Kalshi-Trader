
import csv
import sys
import argparse
from collections import defaultdict
from pathlib import Path
from datetime import datetime

def analyze_structure(log_file, target_time=None):
    tickers = set()
    latest_prices = {}
    
    with open(log_file, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get("market_ticker")
            if not ticker: continue
            
            ts_str = row.get("timestamp")
            if target_time and ts_str > target_time:
                break
                
            tickers.add(ticker)
            
            # Store latest Yes Ask (Best price to Buy Yes)
            # and Yes Bid (Best price to Sell Yes)
            latest_prices[ticker] = {
                "yes_ask": row.get("implied_yes_ask"),
                "yes_bid": row.get("best_yes_bid"),
                "no_ask": row.get("implied_no_ask"),
                "no_bid": row.get("best_no_bid"),
                "ts": ts_str
            }

    print(f"Analysis for {log_file} at {target_time or 'END'}")
    print(f"Found {len(tickers)} unique tickers.")
    
    sorted_tickers = sorted(list(tickers))
    
    print(f"{'Ticker':<25} | {'Yes Bid':<8} | {'Yes Ask':<8} | {'No Bid':<8} | {'No Ask':<8} | {'Last Upd'}")
    print("-" * 90)
    
    for t in sorted_tickers:
        p = latest_prices.get(t)
        if p:
            print(f"{t:<25} | {p['yes_bid']:<8} | {p['yes_ask']:<8} | {p['no_bid']:<8} | {p['no_ask']:<8} | {p['ts']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("log_file")
    parser.add_argument("--time", help="Snapshot time (ISO format)")
    args = parser.parse_args()
    
    analyze_structure(args.log_file, args.time)
