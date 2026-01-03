import pandas as pd
import re
import os
from datetime import datetime, timedelta

# Paths
VM_LOGS_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs"
TRADES_FILE = os.path.join(VM_LOGS_DIR, "trades.csv")
TRADER_LOG = os.path.join(VM_LOGS_DIR, "live_trader_v4.log")

def calculate_expected_fee(price, qty):
    p = price / 100.0
    raw_fee = 0.07 * qty * p * (1 - p)
    import math
    fee = math.ceil(raw_fee * 100) / 100.0
    return fee

def analyze_trades():
    print("Loading trades...")
    df_trades = pd.read_csv(TRADES_FILE)
    df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
    
    # Filter since Dec 23 (start of available logs)
    df_trades = df_trades[df_trades['timestamp'] >= '2025-12-23']
    
    if df_trades.empty:
        print("No trades found since Dec 23.")
        return

    print(f"Analyzing {len(df_trades)} trades...")
    
    # Parse log for TICK and TRY_ORDER
    tick_data = {} # (ticker, timestamp_str) -> {ya, na}
    try_orders = {} # (ticker, timestamp_str) -> {price, qty}
    
    print("Parsing trader log for SIGNALS using Status-based timing...")
    signals = []
    
    # We need to infer the date. Let's start with the first trade date in trades.csv
    # or just assume the log starts around Dec 23/24.
    # Better: Use the first trade in trades.csv as a hint, but we need to sync with the log.
    # The log starts with "Starting Live Trader V4..."
    # Let's assume the log starts on Dec 23 (based on our previous check) and track rollovers.
    
    current_date = datetime(2025, 12, 23).date()
    last_status_time = None
    
    if os.path.exists(TRADER_LOG):
        with open(TRADER_LOG, 'r', errors='ignore') as f:
            for line in f:
                # --- Status @ 13:25:13 ---
                status_match = re.search(r'--- Status @ (\d{2}:\d{2}:\d{2}) ---', line)
                if status_match:
                    t_str = status_match.group(1)
                    t = datetime.strptime(t_str, "%H:%M:%S").time()
                    
                    # Check for day rollover (e.g. 23:59 -> 00:00)
                    if last_status_time and t < last_status_time:
                        # Heuristic: if jump is large (backwards), it's a new day
                        # e.g. 23:59 to 00:00 is a jump of -23h59m
                        current_date += timedelta(days=1)
                        # print(f"Log Date Rollover to {current_date}")
                    
                    last_status_time = t
                    continue

                # Look for SIGNAL
                # SIGNAL KXHIGHNY-25DEC24-B46.5 1 | SIGNAL BUY_YES 3 @ 11
                if "SIGNAL" in line and "BUY" in line and last_status_time:
                    sig_match = re.search(r'SIGNAL (\S+) \d+ \| SIGNAL (BUY_\w+) (\d+) @ (\d+)', line)
                    if sig_match:
                        ticker, action, qty, price = sig_match.groups()
                        
                        # Assign timestamp based on last_status_time
                        # This is an APPROXIMATION (signals happen *after* the status log usually? 
                        # Actually status is printed periodically. Signals happen in between.
                        # We'll assign the last_status_time as the "anchor".
                        # Trades in trades.csv will be matched if they are "close enough" (e.g. within 2 mins)
                        
                        sig_dt = datetime.combine(current_date, last_status_time)
                        
                        signals.append({
                            'ts': sig_dt,
                            'ticker': ticker,
                            'action': action,
                            'qty': int(qty),
                            'price': int(price),
                            'type': 'SIGNAL'
                        })

    print(f"Found {len(signals)} signals.")
    signals.sort(key=lambda x: x['ts'])

    results = []
    fill_ratios = []
    latencies = []

    for _, trade in df_trades.iterrows():
        trade_ts = trade['timestamp']
        ticker = trade['ticker']
        
        matched_signal = None
        min_diff = float('inf')
        
        # Find closest signal within 2 MINUTES
        # CRITICAL: The signal must be BEFORE or AT the trade time (with small tolerance for clock skew)
        # But since our signal time is "quantized" to the LAST status time, the signal time might be
        # significantly BEFORE the trade time (up to 60s).
        # It should RARELY be AFTER the trade time (unless we matched to the NEXT status window).
        
        # Let's filter signals that are:
        # 1. Same Ticker & Action
        # 2. Signal Time <= Trade Time + 5s (allow small skew)
        # 3. Signal Time >= Trade Time - 120s (don't match too old)
        
        relevant_signals = [s for s in signals if 
                            s['ticker'] == ticker and 
                            s['action'] == trade['action'] and 
                            (trade_ts - s['ts']).total_seconds() >= -5.0 and
                            (trade_ts - s['ts']).total_seconds() < 120.0]
        
        # Sort by proximity to trade time (closest first)
        relevant_signals.sort(key=lambda s: abs((trade_ts - s['ts']).total_seconds()))
        
        # Heuristic: Prefer signal where qty >= trade_qty (if possible)
        # But if it's a partial fill, qty < signal_qty.
        # If we have multiple candidates, pick the one closest in time.
        
        if relevant_signals:
            matched_signal = relevant_signals[0]
            min_diff = abs((trade_ts - matched_signal['ts']).total_seconds())
        else:
            matched_signal = None
            min_diff = None
        
        expected_price = matched_signal['price'] if matched_signal else None
        signal_qty = matched_signal['qty'] if matched_signal else None
        
        # Fill Analysis
        fill_ratio = None
        if signal_qty:
            fill_ratio = trade['qty'] / signal_qty
            fill_ratios.append(fill_ratio)
        
        # Latency Analysis (Not accurate with this method, so skip or mark approx)
        latency_ms = None 
        # We can't calculate ms latency because signal ts is quantized to minute boundaries.

        results.append({
            'timestamp': trade['timestamp'],
            'ticker': ticker,
            'action': trade['action'],
            'actual_price': trade['price'],
            'expected_price': expected_price,
            'actual_qty': trade['qty'],
            'signal_qty': signal_qty,
            'fill_ratio': fill_ratio,
            'latency_ms': latency_ms,
            'match_diff_sec': min_diff if matched_signal else None
        })

    df_res = pd.DataFrame(results)
    
    print("\n=== Fill Probability Analysis ===")
    if fill_ratios:
        avg_fill = sum(fill_ratios) / len(fill_ratios)
        print(f"Average Fill Ratio: {avg_fill*100:.2f}%")
        partial_fills = [r for r in fill_ratios if r < 1.0]
        print(f"Partial Fills: {len(partial_fills)} / {len(fill_ratios)}")
        if partial_fills:
            print(f"  (Trades where we got less than requested)")
    else:
        print("No matched signals to calculate fill ratio.")

    print("\n=== Latency Analysis ===")
    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        min_lat = min(latencies)
        print(f"Average Latency (Signal -> Trade): {avg_lat:.2f} ms")
        print(f"Min Latency: {min_lat:.2f} ms")
        print(f"Max Latency: {max_lat:.2f} ms")
    else:
        print("No matched signals to calculate latency.")

    df_res.to_csv("fill_latency_analysis.csv", index=False)
    print("\nDetailed report saved to fill_latency_analysis.csv")

if __name__ == "__main__":
    analyze_trades()
