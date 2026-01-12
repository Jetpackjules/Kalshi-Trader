import sys
import os
import argparse
from datetime import datetime, timedelta, time
from pathlib import Path

# Add server_mirror to path to ensure we use the correct code
sys.path.insert(0, os.path.join(os.getcwd(), "server_mirror"))

from server_mirror.unified_engine.engine import UnifiedEngine
from server_mirror.unified_engine.adapters import SimAdapter
from server_mirror.unified_engine.tick_sources import iter_ticks_from_market_logs
from server_mirror.backtesting.strategies.v3_variants import hb_notional_010
from server_mirror.backtesting.engine import parse_market_date_from_ticker
import json

def main():
    parser = argparse.ArgumentParser(description="Run Unified Backtest (Shadow Mode)")
    parser.add_argument("--out-dir", type=str, default="unified_engine_out", help="Output directory")
    parser.add_argument("--snapshot", type=str, default=r"vm_logs\snapshots\snapshot_2026-01-08_173738.json", help="Path to snapshot JSON")
    parser.add_argument("--start-ts", type=str, default="2026-01-08 17:37:38", help="Simulation start timestamp (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--end-ts", type=str, default="2099-01-01 00:00:00", help="Simulation end timestamp (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--initial-cash", type=float, default=2.12, help="Initial cash balance")
    parser.add_argument("--min-requote-interval", type=float, default=1.0, help="Minimum interval between orders (seconds)")
    parser.add_argument("--warmup-hours", type=int, default=48, help="Hours of data to feed before start-ts")
    parser.add_argument("--strategy", type=str, default="hb_notional_010", help="Strategy function name from v3_variants")
    parser.add_argument("--trade-all-day", action="store_true", help="Disable time constraints for the strategy")
    args = parser.parse_args()

    print(f"Running Unified Backtest (Shadow Mode) - Strategy: {args.strategy}...")
    
    # Configuration
    log_dir = r"vm_logs\market_logs"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    start_ts = datetime.strptime(args.start_ts, "%Y-%m-%d %H:%M:%S")
    end_ts = datetime.strptime(args.end_ts, "%Y-%m-%d %H:%M:%S")
    warmup_start_ts = start_ts - timedelta(hours=args.warmup_hours)
    
    initial_cash = args.initial_cash
    min_requote_interval = args.min_requote_interval
    
    # Initialize Strategy
    import server_mirror.backtesting.strategies.v3_variants as v3_variants
    strat_func = getattr(v3_variants, args.strategy)
    strategy = strat_func()
    
    if args.trade_all_day:
        print("Disabling time constraints (trade-all-day)...")
        strategy.active_hours = list(range(24))
    
    print(f"Loaded Strategy: {strategy.name}")
    
    # Load Snapshot
    snapshot_path = args.snapshot
    print(f"Loading snapshot from: {snapshot_path}")
    with open(snapshot_path, "r") as f:
        snapshot = json.load(f)
    
    initial_positions = snapshot.get("positions", {})
    print(f"Loaded {len(initial_positions)} initial positions from snapshot.")

    # Initialize Adapter
    adapter = SimAdapter(
        initial_cash=initial_cash,
        initial_positions=initial_positions,
        diag_log=None
    )
    
    # Initialize Engine
    engine = UnifiedEngine(
        strategy=strategy,
        adapter=adapter,
        min_requote_interval=min_requote_interval,
        diag_log=None,
        decision_log=None # Can enable if needed
    )
    
    # Load Ticks
    print(f"Loading ticks from {log_dir}...")
    ticks = iter_ticks_from_market_logs(log_dir)
    
    # Run Loop
    print(f"Starting Warmup from {warmup_start_ts} to {start_ts}...")
    print(f"Simulation Start: {start_ts}")
    
    count = 0
    warmup_count = 0
    
    for tick in ticks:
        t = tick['time']
        
        if t < warmup_start_ts:
            continue
            
        if t > end_ts:
            break
            
        if t < start_ts:
            # Warmup Phase: Feed strategy but ignore orders
            # Construct minimal state required by RegimeSwitcher
            # portfolios_inventories = dict { 'MM': {'YES': qty, 'NO': qty}, ... }
            # We assume empty inventory during warmup for simplicity, 
            # or we could track it if we wanted to simulate warmup trades (but we don't want to execute them).
            # The strategy updates its HISTORY (fair prices, spreads) regardless of inventory.
            
            warmup_count += 1
            if warmup_count % 10000 == 0:
                print(f"Warmup processed {warmup_count} ticks... Current: {t}")
                
            # Mock inputs
            # We assume 'MM' inventory is empty during warmup
            portfolios_inventories = {'MM': {'YES': 0, 'NO': 0}}
            active_orders = []
            spendable_cash = initial_cash
            
            strategy.on_market_update(
                tick['ticker'],
                tick['market_state'],
                t,
                portfolios_inventories,
                active_orders,
                spendable_cash
            )
            continue
            
        # Simulation Phase
        count += 1
        if count % 10000 == 0:
            print(f"Sim processed {count} ticks... Current: {t}")
            
        engine.on_tick(
            ticker=tick['ticker'],
            market_state=tick['market_state'],
            current_time=t,
            tick_seq=tick.get('seq'),
            tick_source=tick.get('source_file'),
            tick_row=tick.get('source_row')
        )
        
        # --- DYNAMIC SETTLEMENT PAYOUT ---
        # Settle any market at 5 AM the day after its market date
        if not 'settled_dates' in locals(): settled_dates = set()
        
        # Check for any positions that can be settled
        for ticker in list(adapter.positions.keys()):
            m_dt = parse_market_date_from_ticker(ticker)
            if m_dt:
                settle_dt = datetime.combine(m_dt.date() + timedelta(days=1), time(5, 0, 0))
                if t >= settle_dt and (ticker, m_dt.date()) not in settled_dates:
                    # Determine settlement price (100 if >= 50, else 0)
                    # We use the last known price from the adapter's history or market state
                    # For simplicity in this runner, we'll use the last price seen by the adapter
                    last_price = adapter.last_prices.get(ticker, 50.0) # Default to 50 if unknown
                    settle_price = 100.0 if last_price >= 50.0 else 0.0
                    
                    print(f"*** SETTLING {ticker} at {t} (Price: {settle_price}) ***")
                    payout = adapter.settle_market(ticker, settle_price, t)
                    print(f"*** Payout: ${payout:.2f} | New Cash: ${adapter.cash:.2f} ***")
                    settled_dates.add((ticker, m_dt.date()))
        # ----------------------------------
        
    print("Backtest Complete.")
    print(f"Trades: {len(adapter.trades)}")
    
    final_cash = adapter.get_cash()
    print(f"Final Cash: ${final_cash:.2f}")
    
    print("\nFinal Holdings:")
    total_mtm = 0.0
    positions = adapter.get_positions()
    if not positions:
        print("  None")
    else:
        for ticker, pos in positions.items():
            yes_qty = pos.get("yes", 0)
            no_qty = pos.get("no", 0)
            last_yes_price = adapter.last_prices.get(ticker, 0.0)
            
            if yes_qty > 0:
                mark_price = last_yes_price
                val = yes_qty * (mark_price / 100.0)
                pos_str = f"{yes_qty} YES"
            else:
                mark_price = 100.0 - last_yes_price
                val = no_qty * (mark_price / 100.0)
                pos_str = f"{no_qty} NO"
            
            total_mtm += val
            print(f"  {ticker:25} | {pos_str:8} | Mark Price: {mark_price:5.1f} | Value: ${val:6.2f}")
    
    print(f"\nTotal MTM Value: ${total_mtm:.2f}")
    print(f"Total Portfolio Value: ${final_cash + total_mtm:.2f}")
    
    # Export Trades
    import pandas as pd
    trades_df = pd.DataFrame(adapter.trades)
    trades_df.to_csv(out_dir / "unified_trades.csv", index=False)
    print(f"\nSaved trades to {out_dir / 'unified_trades.csv'}")

if __name__ == "__main__":
    main()
