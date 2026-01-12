import sys
import os
import csv
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from server_mirror.backtesting.engine import ComplexBacktester
from server_mirror.backtesting.strategies.v3_variants import hb_notional_010

def main():
    print("Running shadow backtest with history seeding...")
    
    # Snapshot parameters
    start_dt = datetime(2026, 1, 8, 17, 37, 38)
    end_dt = datetime(2026, 1, 10, 10, 31, 41)
    initial_capital = 2.12 # From snapshot_2026-01-08_173738.json
    
    # Configure backtester
    backtester = ComplexBacktester(
        strategies=[hb_notional_010()],
        start_datetime=start_dt,
        end_datetime=end_dt,
        initial_capital=initial_capital,
        seed_warmup_from_history=True, # ENABLE THE FIX
        log_dir=r"vm_logs\market_logs",
        generate_daily_charts=False,
        generate_final_chart=False,
        min_requote_interval_seconds=1.0
    )
    
    # Run
    backtester.run()
    
    # Export trades
    trades = []
    for s_name, portfolio in backtester.portfolios.items():
        for t in portfolio['trades']:
            trades.append(t)
            
    # Sort trades by time
    trades.sort(key=lambda x: x['time'])

    # Write CSV
    out_dir = "unified_engine_out_snapshot_live"
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "unified_trades.csv")
    
    print(f"Exporting {len(trades)} trades to {out_file}...")
    
    with open(out_file, "w", newline="") as f:
        # Fieldnames based on what ComplexBacktester produces + what graph script expects
        fieldnames = ["time", "action", "price", "qty", "fee", "ticker", "source", "cost", "spread", "capital_after", "slippage", "mid_at_fill", "viz_y", "note"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for t in trades:
            writer.writerow(t)

    print("Backtest complete.")

if __name__ == "__main__":
    main()
