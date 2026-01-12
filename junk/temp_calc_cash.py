import sys
import os
import json
from datetime import datetime
sys.path.append('tools')
import generate_live_vs_backtest_cash_graph as lib

snapshot_path = "vm_logs/snapshots/snapshot_2026-01-08_173738.json"
backtest_trades_path = "unified_engine_out_comparison_recent/unified_trades.csv"
live_trades_path = "vm_logs/unified_engine_out/trades.csv"
market_dir = "vm_logs/market_logs"

# We need to cover enough time to include the snapshot and the target window
start_dt = datetime(2026, 1, 8, 17, 37, 38)
end_dt = datetime(2026, 1, 10, 12, 0, 0)

print("Computing Backtest cash series...")
backtest_series = lib._compute_backtest_cash(backtest_trades_path, snapshot_path, market_dir, start_dt, end_dt)

print("Computing Live cash series (reconstructed)...")
live_series = lib._compute_backtest_cash(live_trades_path, snapshot_path, market_dir, start_dt, end_dt)

target_start = datetime(2026, 1, 9, 5, 3, 30)
target_end = datetime(2026, 1, 10, 0, 0, 0)

def get_cash_at(series, dt):
    last_val = 2.12 # Initial
    for p in series:
        t = datetime.fromisoformat(p['time'])
        if t > dt:
            return last_val
        last_val = p['cash']
    return last_val

bt_in = get_cash_at(backtest_series, target_start)
bt_out = get_cash_at(backtest_series, target_end)

live_in = get_cash_at(live_series, target_start)
live_out = get_cash_at(live_series, target_end)

print("-" * 30)
print(f"Time Window: {target_start} -> {target_end}")
print("-" * 30)
print(f"BACKTEST:")
print(f"  Going In:  ${bt_in:.2f}")
print(f"  Going Out: ${bt_out:.2f}")
print(f"  Net Change: ${bt_out - bt_in:.2f}")
print("-" * 30)
print(f"LIVE (Reconstructed):")
print(f"  Going In:  ${live_in:.2f}")
print(f"  Going Out: ${live_out:.2f}")
print(f"  Net Change: ${live_out - live_in:.2f}")
print("-" * 30)
