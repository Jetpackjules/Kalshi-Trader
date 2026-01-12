import sys
import os
import argparse
import time as time_module
from datetime import datetime, timedelta, time
from pathlib import Path
import json

# Add server_mirror to path to ensure we use the correct code
sys.path.insert(0, os.path.join(os.getcwd(), "server_mirror"))

from server_mirror.unified_engine.engine import UnifiedEngine
from server_mirror.unified_engine.adapters import SimAdapter
from server_mirror.unified_engine.tick_sources import iter_ticks_from_market_logs
from server_mirror.backtesting.engine import parse_market_date_from_ticker


def _compute_holdings(adapter: SimAdapter) -> float:
    holdings = 0.0
    positions = adapter.get_positions()
    for ticker, pos in positions.items():
        yes_qty = int(pos.get("yes") or 0)
        no_qty = int(pos.get("no") or 0)
        last_price = adapter.last_prices.get(ticker, 50.0)
        holdings += yes_qty * (last_price / 100.0)
        holdings += no_qty * ((100.0 - last_price) / 100.0)
    return holdings


def main():
    parser = argparse.ArgumentParser(description="Run Unified Backtest (Shadow Mode)")
    parser.add_argument("--out-dir", type=str, default="unified_engine_out", help="Output directory")
    parser.add_argument(
        "--snapshot",
        type=str,
        default=r"vm_logs\snapshots\snapshot_2026-01-08_173738.json",
        help="Path to snapshot JSON",
    )
    parser.add_argument(
        "--start-ts",
        type=str,
        default="2026-01-08 17:37:38",
        help="Simulation start timestamp (YYYY-MM-DD HH:MM:SS)",
    )
    parser.add_argument(
        "--end-ts",
        type=str,
        default="2099-01-01 00:00:00",
        help="Simulation end timestamp (YYYY-MM-DD HH:MM:SS)",
    )
    parser.add_argument("--initial-cash", type=float, default=2.12, help="Initial cash balance")
    parser.add_argument(
        "--min-requote-interval",
        type=float,
        default=1.0,
        help="Minimum interval between orders (seconds)",
    )
    parser.add_argument("--warmup-hours", type=int, default=48, help="Hours of data to feed before start-ts")
    parser.add_argument(
        "--strategy",
        type=str,
        default="hb_notional_010",
        help="Strategy function name from v3_variants",
    )
    parser.add_argument("--trade-all-day", action="store_true", help="Disable time constraints for the strategy")
    parser.add_argument("--max-loss-pct", type=float, default=None, help="Override max_loss_pct for the strategy")
    parser.add_argument(
        "--strategy-kwargs",
        type=str,
        default="{}",
        help="JSON string of extra arguments for the strategy",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose/debug output")
    parser.add_argument("--quiet", action="store_true", help="Suppress non-error output")
    args = parser.parse_args()

    os.environ["BT_VERBOSE"] = "1" if args.verbose else "0"

    def log(message: str) -> None:
        if not args.quiet:
            print(message)

    log(f"Running Unified Backtest (Shadow Mode) - Strategy: {args.strategy}...")

    log_dir = r"vm_logs\market_logs"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_ts = datetime.strptime(args.start_ts, "%Y-%m-%d %H:%M:%S")
    end_ts = datetime.strptime(args.end_ts, "%Y-%m-%d %H:%M:%S")
    warmup_start_ts = start_ts - timedelta(hours=args.warmup_hours)

    initial_cash = args.initial_cash
    min_requote_interval = args.min_requote_interval

    import server_mirror.backtesting.strategies.v3_variants as v3_variants

    strat_func = getattr(v3_variants, args.strategy)

    strategy_kwargs = json.loads(args.strategy_kwargs)
    try:
        strategy = strat_func(**strategy_kwargs)
    except TypeError:
        strategy = strat_func()

    if args.max_loss_pct is not None:
        try:
            if hasattr(strategy, "mm") and hasattr(strategy.mm, "max_loss_pct"):
                strategy.mm.max_loss_pct = float(args.max_loss_pct)
            if hasattr(strategy, "max_loss_pct"):
                strategy.max_loss_pct = float(args.max_loss_pct)
        except (TypeError, ValueError):
            pass

    if args.trade_all_day:
        log("Disabling time constraints (trade-all-day)...")
        strategy.active_hours = list(range(24))

    log(f"Loaded Strategy: {strategy.name}")

    snapshot_path = args.snapshot
    log(f"Loading snapshot from: {snapshot_path}")
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    initial_positions = snapshot.get("positions", {})
    log(f"Loaded {len(initial_positions)} initial positions from snapshot.")

    adapter = SimAdapter(
        initial_cash=initial_cash,
        initial_positions=initial_positions,
        diag_log=None,
    )

    engine = UnifiedEngine(
        strategy=strategy,
        adapter=adapter,
        min_requote_interval=min_requote_interval,
        diag_log=None,
        decision_log=None,
    )

    log(f"Loading ticks from {log_dir}...")
    ticks = iter_ticks_from_market_logs(log_dir)

    log(f"Starting Warmup from {warmup_start_ts} to {start_ts}...")
    log(f"Simulation Start: {start_ts}")

    count = 0
    warmup_count = 0
    sim_start_perf_time = time_module.perf_counter()
    equity_history = []
    equity_breakdowns = []
    last_history_date = None
    started = False

    def record_equity(record_date: datetime.date) -> None:
        cash_val = adapter.get_cash()
        holdings_val = _compute_holdings(adapter)
        equity_val = cash_val + holdings_val
        equity_history.append(
            {
                "date": record_date.isoformat(),
                "equity": equity_val,
                "cash": cash_val,
                "holdings": holdings_val,
            }
        )
        positions = adapter.get_positions()
        for ticker, pos in positions.items():
            yes_qty = int(pos.get("yes") or 0)
            no_qty = int(pos.get("no") or 0)
            last_price = adapter.last_prices.get(ticker, 50.0)
            value = (yes_qty * (last_price / 100.0)) + (no_qty * ((100.0 - last_price) / 100.0))
            equity_breakdowns.append(
                {
                    "date": record_date.isoformat(),
                    "ticker": ticker,
                    "yes_qty": yes_qty,
                    "no_qty": no_qty,
                    "last_price": last_price,
                    "value": value,
                    "cash": cash_val,
                    "equity": equity_val,
                }
            )

    settled_dates: set[tuple[str, datetime.date]] = set()

    for tick in ticks:
        t = tick["time"]

        if t < warmup_start_ts:
            continue

        if t > end_ts:
            break

        if t < start_ts:
            warmup_count += 1
            if warmup_count % 10000 == 0:
                if args.verbose and not args.quiet:
                    print(f"Warmup processed {warmup_count} ticks... Current: {t}")

            portfolios_inventories = {"MM": {"YES": 0, "NO": 0}}
            active_orders = []
            spendable_cash = initial_cash

            strategy.on_market_update(
                tick["ticker"],
                tick["market_state"],
                t,
                portfolios_inventories,
                active_orders,
                spendable_cash,
            )
            continue

        if not started:
            last_history_date = t.date()
            started = True
        elif t.date() != last_history_date:
            record_equity(last_history_date)
            last_history_date = t.date()

        count += 1
        if count % 10000 == 0:
            if not args.quiet:
                total_sim_seconds = (end_ts - start_ts).total_seconds()
                current_sim_seconds = (t - start_ts).total_seconds()

                if total_sim_seconds > 0 and current_sim_seconds > 0:
                    progress = current_sim_seconds / total_sim_seconds
                    elapsed_real = time_module.perf_counter() - sim_start_perf_time

                    if progress > 0:
                        eta_seconds = (elapsed_real / progress) - elapsed_real
                        eta_str = time_module.strftime(
                            "%H:%M:%S", time_module.gmtime(max(0, eta_seconds))
                        )
                        print(
                            f"[Progress: {progress*100:5.1f}%] ETA: {eta_str} | Current: {t}          ",
                            end="\r",
                            flush=True,
                        )
                    else:
                        print(f"Sim processed {count} ticks... Current: {t}")
                else:
                    print(f"Sim processed {count} ticks... Current: {t}")

        engine.on_tick(
            ticker=tick["ticker"],
            market_state=tick["market_state"],
            current_time=t,
            tick_seq=tick.get("seq"),
            tick_source=tick.get("source_file"),
            tick_row=tick.get("source_row"),
        )

        for ticker in list(adapter.positions.keys()):
            m_dt = parse_market_date_from_ticker(ticker)
            if m_dt:
                settle_dt = datetime.combine(m_dt.date() + timedelta(days=1), time(5, 0, 0))
                if t >= settle_dt and (ticker, m_dt.date()) not in settled_dates:
                    last_price = adapter.last_prices.get(ticker, 50.0)
                    settle_price = 100.0 if last_price >= 50.0 else 0.0

                    if args.verbose and not args.quiet:
                        print(f"*** SETTLING {ticker} at {t} (Price: {settle_price}) ***")
                    payout = adapter.settle_market(ticker, settle_price, t)
                    if args.verbose and not args.quiet:
                        print(f"*** Payout: ${payout:.2f} | New Cash: ${adapter.cash:.2f} ***")
                    settled_dates.add((ticker, m_dt.date()))

    log("Backtest Complete.")
    log(f"Trades: {len(adapter.trades)}")

    final_cash = adapter.get_cash()
    log(f"Final Cash: ${final_cash:.2f}")

    log("\nFinal Holdings:")
    total_mtm = 0.0
    positions = adapter.get_positions()
    if not positions:
        log("  None")
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
            log(
                f"  {ticker:25} | {pos_str:8} | Mark Price: {mark_price:5.1f} | Value: ${val:6.2f}"
            )

    log(f"\nTotal MTM Value: ${total_mtm:.2f}")
    print(f"Total Portfolio Value: ${final_cash + total_mtm:.2f}")

    import pandas as pd

    trades_df = pd.DataFrame(adapter.trades)
    trades_df.to_csv(out_dir / "unified_trades.csv", index=False)
    if last_history_date is not None:
        record_equity(last_history_date)
    if equity_history:
        equity_df = pd.DataFrame(equity_history)
        equity_df.to_csv(out_dir / "equity_history.csv", index=False)
    if equity_breakdowns:
        breakdown_df = pd.DataFrame(equity_breakdowns)
        breakdown_df.to_csv(out_dir / "equity_breakdown.csv", index=False)
    log(f"\nSaved trades to {out_dir / 'unified_trades.csv'}")


if __name__ == "__main__":
    main()
