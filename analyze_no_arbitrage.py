import csv
import os
import glob
from collections import defaultdict

def parse_float(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None

def analyze_no_arbitrage(path):
    # 1. First pass: Identify the Universe of Tickers
    universe = set()
    rows = []
    
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return None
            
            for row in reader:
                ticker = row.get("market_ticker")
                if ticker:
                    universe.add(ticker)
                rows.append(row)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return None

    if not universe:
        return None

    # 2. Second pass: Replay and Track No Asks
    current_no_asks = {} # ticker -> price
    anomalies = []
    events = [] # List of {"start": ts, "end": ts, "max_profit": float, "duration": float}
    
    in_event = False
    event_start_ts = None
    event_max_profit = -1000.0
    
    max_profit_overall = -1000.0
    best_strategy = None
    
    # Sort rows by timestamp to ensure correct duration calculation
    rows.sort(key=lambda x: x.get("timestamp", ""))
    
    from datetime import datetime
    
    def get_ts(row):
        return row.get("timestamp")

    for i, row in enumerate(rows):
        ticker = row.get("market_ticker")
        na = parse_float(row.get("implied_no_ask"))
        ts = row.get("timestamp")
        
        is_profitable = False
        current_tick_profit = 0.0
        
        if ticker and na is not None:
            current_no_asks[ticker] = na
            
            if len(current_no_asks) >= 2:
                prices = sorted(current_no_asks.values())
                
                # Check for ANY profitable k
                for k in range(2, len(prices) + 1):
                    cost = sum(prices[:k])
                    revenue = (k - 1) * 100
                    profit = revenue - cost
                    
                    if profit > 0:
                        is_profitable = True
                        if profit > current_tick_profit:
                            current_tick_profit = profit
                        
                        # Track best overall
                        if profit > max_profit_overall:
                            max_profit_overall = profit
                            best_strategy = {
                                "timestamp": ts,
                                "k": k,
                                "profit": profit,
                                "cost": cost,
                                "prices": prices[:k]
                            }
        
        # Event Logic
        if is_profitable:
            if not in_event:
                in_event = True
                event_start_ts = ts
                event_max_profit = current_tick_profit
            else:
                if current_tick_profit > event_max_profit:
                    event_max_profit = current_tick_profit
        else:
            if in_event:
                in_event = False
                # Close event
                try:
                    s = datetime.fromisoformat(event_start_ts)
                    e = datetime.fromisoformat(ts)
                    duration = (e - s).total_seconds()
                    events.append({
                        "start": event_start_ts,
                        "end": ts,
                        "max_profit": event_max_profit,
                        "duration": duration
                    })
                except:
                    pass

    # Close final event if open
    if in_event:
        try:
            s = datetime.fromisoformat(event_start_ts)
            e = datetime.fromisoformat(rows[-1].get("timestamp"))
            duration = (e - s).total_seconds()
            events.append({
                "start": event_start_ts,
                "end": rows[-1].get("timestamp"),
                "max_profit": event_max_profit,
                "duration": duration
            })
        except:
            pass

    return {
        "universe_size": len(universe),
        "anomalies": anomalies, # Empty now to save memory/noise if we don't need tick-level
        "max_profit": max_profit_overall,
        "best_strategy": best_strategy,
        "events": events
    }

def main():
    log_dirs = [
        "server_mirror/market_logs",
        "local_market_logs"
    ]
    target_file = "market_data_KXHIGHNY-26JAN*.csv"
    
    print(f"Analyzing 'Guaranteed No Profit' Duration for {target_file} (Excluding Jan 1-3)...")
    
    all_events = []
    
    for log_dir in log_dirs:
        files = glob.glob(os.path.join(log_dir, target_file))
        
        for f in files:
            # Exclude Jan 1-3
            basename = os.path.basename(f)
            if "26JAN01" in basename or "26JAN02" in basename or "26JAN03" in basename:
                continue
                
            result = analyze_no_arbitrage(f)
            if result and result["events"]:
                all_events.extend(result["events"])
                print(f"Found {len(result['events'])} events in {basename}")

    if not all_events:
        print("No events found.")
        return

    # Statistics
    import statistics
    
    durations = [e["duration"] for e in all_events]
    avg_duration = statistics.mean(durations)
    
    profits = [e["max_profit"] for e in all_events]
    avg_profit = statistics.mean(profits)
    
    # Top 10 Longest
    longest = sorted(all_events, key=lambda x: x["duration"], reverse=True)[:10]
    avg_longest = statistics.mean([e["duration"] for e in longest])
    
    # Top 10 Most Profitable
    most_profitable = sorted(all_events, key=lambda x: x["max_profit"], reverse=True)[:10]
    avg_most_profitable = statistics.mean([e["duration"] for e in most_profitable])
    
    print("\n" + "="*30)
    print("DURATION & PROFIT ANALYSIS (Excluding Jan 1-3)")
    print("="*30)
    print(f"Total Events: {len(all_events)}")
    print(f"Average Duration:             {avg_duration:.2f} seconds")
    print(f"Average Profit:               {avg_profit:.2f} cents")
    print("-" * 30)
    print(f"Average Duration (Top 10 Longest): {avg_longest:.2f} seconds")
    print("Top 10 Longest Events:")
    for i, e in enumerate(longest):
        print(f"  {i+1}. {e['duration']:.2f}s (Profit: {e['max_profit']:.2f}c) @ {e['start']}")
    print("-" * 30)
    print(f"Average Duration (Top 10 Most Profitable): {avg_most_profitable:.2f} seconds")
    print("Top 10 Most Profitable Events:")
    for i, e in enumerate(most_profitable):
        print(f"  {i+1}. Profit: {e['max_profit']:.2f}c (Duration: {e['duration']:.2f}s) @ {e['start']}")
    print("="*30)
    
    # Top 10% Analysis
    top_10_percent_count = max(1, int(len(all_events) * 0.1))
    top_10_percent_events = sorted(all_events, key=lambda x: x["max_profit"], reverse=True)[:top_10_percent_count]
    
    avg_profit_top_10_percent = statistics.mean([e["max_profit"] for e in top_10_percent_events])
    avg_duration_top_10_percent = statistics.mean([e["duration"] for e in top_10_percent_events])
    
    print("\n" + "="*30)
    print(f"TOP 10% ANALYSIS (Top {top_10_percent_count} events)")
    print("="*30)
    print(f"Average Profit (Top 10%):       {avg_profit_top_10_percent:.2f} cents")
    print(f"Average Duration (Top 10%):     {avg_duration_top_10_percent:.2f} seconds")
    print("="*30)

if __name__ == "__main__":
    main()
