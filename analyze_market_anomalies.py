import csv
import os
import glob
from pathlib import Path
from collections import defaultdict

def parse_float(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None

def analyze_file(path):
    stats = {
        "total_rows": 0,
        "implied_sum_lt_100": 0,
        "bid_sum_gt_100": 0,
        "rows_with_last_trade": 0,
        "last_trade_sum_lt_100": 0, # This is tricky since we only have one last_trade_price
    }
    
    # We'll track the last known last_trade_price for each ticker to see if we can find pairs
    # But the user asked for "sum of last traded yes and no for the same market"
    # In Kalshi, Yes Price + No Price should = 100.
    # If last_trade_price is 45 (Yes), then implied No is 55.
    # If the user means "sum of last traded Yes and last traded No", we need to find both.
    
    last_trades = {} # ticker -> {"YES": price, "NO": price}
    
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return stats
            
            for row in reader:
                stats["total_rows"] += 1
                ticker = row.get("market_ticker")
                
                # Implied Sum Analysis
                ya = parse_float(row.get("implied_yes_ask"))
                na = parse_float(row.get("implied_no_ask"))
                if ya is not None and na is not None:
                    if ya + na < 100:
                        stats["implied_sum_lt_100"] += 1
                        print(f"[ASK < 100] {path} | {row.get('timestamp')} | {ticker} | YesAsk:{ya} + NoAsk:{na} = {ya+na}")
                
                # Bid Sum Analysis
                yb = parse_float(row.get("best_yes_bid"))
                nb = parse_float(row.get("best_no_bid"))
                if yb is not None and nb is not None:
                    if yb + nb > 100:
                        stats["bid_sum_gt_100"] += 1
                        print(f"[BID > 100] {path} | {row.get('timestamp')} | {ticker} | YesBid:{yb} + NoBid:{nb} = {yb+nb}")
                
                # Last Trade Analysis
                lt = parse_float(row.get("last_trade_price"))
                if lt is not None:
                    stats["rows_with_last_trade"] += 1
                    # Since the logger only records one last_trade_price (usually Yes),
                    # we can't easily find a "sum of last traded yes and no" in a single row
                    # unless we assume the other side is 100 - lt.
                    # But if the user means "last traded Yes + last traded No < 100", 
                    # that would be a massive arbitrage.
                    
                    # Let's track the latest for each ticker
                    if ticker not in last_trades:
                        last_trades[ticker] = {"YES": None, "NO": None}
                    
                    # The logger records last_trade_price which is usually the Yes price.
                    # If we had a No last trade, it would be in a different column or row.
                    # Based on granular_logger.py, it's just 'last_trade_price'.
                    last_trades[ticker]["YES"] = lt
                    
                    # If we assume the user wants to know if (Last Yes + Last No) < 100
                    # and we only have Last Yes... this is ambiguous.
                    # However, if Last Yes + Last No < 100, it means someone sold Yes cheap 
                    # AND someone sold No cheap.
                    
    except Exception as e:
        print(f"Error processing {path}: {e}")
        
    return stats

def main():
    log_dirs = [
        "local_market_logs",
        "server_mirror/market_logs"
    ]
    
    overall_stats = {
        "total_files": 0,
        "total_rows": 0,
        "implied_sum_lt_100": 0,
        "bid_sum_gt_100": 0,
        "rows_with_last_trade": 0,
    }
    
    for log_dir in log_dirs:
        files = glob.glob(os.path.join(log_dir, "market_data_*.csv"))
        for f in files:
            print(f"Analyzing {f}...")
            file_stats = analyze_file(f)
            overall_stats["total_files"] += 1
            overall_stats["total_rows"] += file_stats["total_rows"]
            overall_stats["implied_sum_lt_100"] += file_stats["implied_sum_lt_100"]
            overall_stats["bid_sum_gt_100"] += file_stats["bid_sum_gt_100"]
            overall_stats["rows_with_last_trade"] += file_stats["rows_with_last_trade"]
            
    print("\n" + "="*30)
    print("MARKET ANOMALY REPORT")
    print("="*30)
    print(f"Total Files Analyzed: {overall_stats['total_files']}")
    print(f"Total Rows Scanned:   {overall_stats['total_rows']}")
    print("-" * 30)
    print(f"Implied Sum < 100 (Crossed Asks): {overall_stats['implied_sum_lt_100']}")
    print(f"Bid Sum > 100 (Crossed Bids):     {overall_stats['bid_sum_gt_100']}")
    print(f"Rows with Last Trade Price:       {overall_stats['rows_with_last_trade']}")
    print("="*30)
    print("\nNote: 'Implied Sum < 100' means you could have bought both YES and NO for less than $1 total.")
    print("'Bid Sum > 100' means you could have sold both YES and NO for more than $1 total.")

if __name__ == "__main__":
    main()
