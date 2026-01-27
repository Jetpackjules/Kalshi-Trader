import csv
import os
import glob
from collections import defaultdict
from datetime import datetime

def parse_float(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None

def analyze_portfolio(path):
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

    # 2. Second pass: Replay and Track Portfolio Sum
    current_prices = {} # ticker -> {"price": float, "time": str}
    anomalies = []
    
    in_anomaly = False
    anomaly_start_time = None
    current_anomaly_min_sum = 1000.0
    
    # We want to group consecutive anomalies
    grouped_anomalies = []
    
    for row in rows:
        ticker = row.get("market_ticker")
        ya = parse_float(row.get("implied_yes_ask"))
        ts = row.get("timestamp")
        
        if ticker and ya is not None:
            current_prices[ticker] = {"price": ya, "time": ts}
            
            # Check if we have a full universe
            if len(current_prices) == len(universe):
                # Calculate Sum
                portfolio_sum = sum(item["price"] for item in current_prices.values())
                
                if portfolio_sum < 100:
                    if not in_anomaly:
                        in_anomaly = True
                        anomaly_start_time = ts
                        current_anomaly_min_sum = portfolio_sum
                    
                    if portfolio_sum < current_anomaly_min_sum:
                        current_anomaly_min_sum = portfolio_sum
                        
                    anomalies.append({
                        "timestamp": ts,
                        "sum": portfolio_sum,
                        "details": current_prices.copy()
                    })
                else:
                    if in_anomaly:
                        in_anomaly = False
                        # Anomaly ended
                        grouped_anomalies.append({
                            "start": anomaly_start_time,
                            "end": ts,
                            "min_sum": current_anomaly_min_sum
                        })

    if in_anomaly:
         grouped_anomalies.append({
            "start": anomaly_start_time,
            "end": rows[-1].get("timestamp"),
            "min_sum": current_anomaly_min_sum
        })

    return {
        "universe_size": len(universe),
        "anomalies": anomalies,
        "grouped_anomalies": grouped_anomalies
    }

def main():
    # Analyze Jan 1st specifically
    log_dirs = [
        "server_mirror/market_logs"
    ]
    target_file = "market_data_KXHIGHNY-26JAN01.csv"
    
    print(f"Analyzing Portfolio Sum for {target_file}...")
    
    for log_dir in log_dirs:
        files = glob.glob(os.path.join(log_dir, target_file))
        # Also check local_market_logs
        files.extend(glob.glob(os.path.join("local_market_logs", target_file)))
        
        for f in files:
            result = analyze_portfolio(f)
            if result and result["anomalies"]:
                count = len(result["anomalies"])
                print(f"Found {count} anomaly ticks in {os.path.basename(f)}")
                
                min_sum = 1000.0
                min_details = None
                
                for a in result["anomalies"]:
                    if a["sum"] < min_sum:
                        min_sum = a["sum"]
                        min_details = a
                
                if min_details:
                    print("\n" + "="*30)
                    print("LOWEST SUM DETAILS")
                    print("="*30)
                    print(f"Trigger Time: {min_details['timestamp']}")
                    print(f"Lowest Sum:   {min_sum:.2f}")
                    print("-" * 30)
                    print(f"{'Ticker':<25} | {'Price':<6} | {'Last Update Time'}")
                    print("-" * 60)
                    for ticker, info in min_details['details'].items():
                        print(f"{ticker:<25} | {info['price']:<6} | {info['time']}")
                    print("="*30)
                    
                    # Find the duration of this specific anomaly event
                    trigger_ts = min_details['timestamp']
                    for group in result["grouped_anomalies"]:
                        if group["start"] <= trigger_ts <= group["end"]:
                            print(f"\nAnomaly Duration Analysis:")
                            print(f"Start: {group['start']}")
                            print(f"End:   {group['end']}")
                            
                            try:
                                s = datetime.fromisoformat(group['start'])
                                e = datetime.fromisoformat(group['end'])
                                duration = (e - s).total_seconds()
                                print(f"Duration: {duration:.3f} seconds")
                            except:
                                print("Duration: Error parsing timestamps")
                            break

if __name__ == "__main__":
    main()
