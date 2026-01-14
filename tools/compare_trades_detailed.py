import csv
import sys
from datetime import datetime, timedelta

def parse_time(ts_str):
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError:
        # Handle cases like "2026-01-12 08:45:02.081036" (space instead of T)
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")

def load_trades(path):
    trades = []
    with open(path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_str = row.get('time') or row.get('timestamp')
            trades.append({
                'time': parse_time(ts_str),
                'ticker': row['ticker'],
                'action': row['action'],
                'price': float(row['price']),
                'qty': int(row['qty']),
                'source': row.get('source', 'UNKNOWN')
            })
    return sorted(trades, key=lambda x: x['time'])

def compare_trades(file1, file2, tolerance_seconds=2.0):
    trades1 = load_trades(file1)
    trades2 = load_trades(file2)
    
    # Filter for Jan 12 only
    start_dt = datetime(2026, 1, 12)
    trades1 = [t for t in trades1 if t['time'] >= start_dt]
    trades2 = [t for t in trades2 if t['time'] >= start_dt]

    print(f"Loaded {len(trades1)} trades from Mimic Backtest")
    print(f"Loaded {len(trades2)} trades from Live Bot")
    print("-" * 80)
    print(f"{'MIMIC BACKTEST':<35} | {'LIVE BOT':<35} | {'STATUS':<10}")
    print("-" * 80)

    matched2 = set()
    
    for t1 in trades1:
        # Find matching trade in t2
        match = None
        for i, t2 in enumerate(trades2):
            if i in matched2: continue
            
            dt = abs((t1['time'] - t2['time']).total_seconds())
            if dt <= tolerance_seconds and t1['ticker'] == t2['ticker'] and t1['action'] == t2['action']:
                match = t2
                matched2.add(i)
                break
        
        t1_str = f"{t1['time'].strftime('%H:%M:%S')} {t1['ticker']} {t1['action']} {t1['qty']}@{t1['price']}"
        
        if match:
            t2_str = f"{match['time'].strftime('%H:%M:%S')} {match['ticker']} {match['action']} {match['qty']}@{match['price']}"
            
            # Check for exact match on price/qty
            if t1['price'] == match['price'] and t1['qty'] == match['qty']:
                status = "MATCH"
            else:
                status = "DIFF"
                
            print(f"{t1_str:<35} | {t2_str:<35} | {status}")
        else:
            print(f"{t1_str:<35} | {'MISSING':<35} | EXTRA")

    # Print extra trades in Live Bot
    for i, t2 in enumerate(trades2):
        if i not in matched2:
            t2_str = f"{t2['time'].strftime('%H:%M:%S')} {t2['ticker']} {t2['action']} {t2['qty']}@{t2['price']}"
            print(f"{'MISSING':<35} | {t2_str:<35} | EXTRA")

if __name__ == "__main__":
    compare_trades(sys.argv[1], sys.argv[2])
