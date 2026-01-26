import sys
import os
import argparse
import csv
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



def _build_decision_logger(path: str | None):
    if not path or path.strip().lower() in {"none", "off"}:
        return None
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    fieldnames = [
        "decision_id",
        "decision_time",
        "tick_time",
        "tick_seq",
        "tick_source",
        "tick_row",
        "ticker",
        "decision_type",
        "cash",
        "pos_yes",
        "pos_no",
        "pending_yes",
        "pending_no",
        "order_index",
        "action",
        "price",
        "qty",
        "source",
    ]
    
    # Initialize file with header
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

    
    def _log(decision: dict) -> None:
        # Re-open in append mode for each write to ensure flush
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            # Filter keys to match fieldnames
            row = {k: v for k, v in decision.items() if k in fieldnames}
            writer.writerow(row)

    return _log


def main():
    parser = argparse.ArgumentParser(description="Run Unified Backtest (Shadow Mode)")
    default_end_ts = "2099-01-01 00:00:00"
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
        default=default_end_ts,
        help="Simulation end timestamp (YYYY-MM-DD HH:MM:SS)",
    )
    parser.add_argument("--initial-cash", type=float, default=2.12, help="Initial cash balance")
    parser.add_argument(
        "--min-requote-interval",
        type=float,
        default=1.0,
        help="Minimum interval between orders (seconds)",
    )
    parser.add_argument("--warmup-hours", type=int, default=0, help="Hours of data to feed before start-ts")
    parser.add_argument(
        "--day-boundary-hour",
        type=int,
        default=0,
        help="Hour offset for daily boundaries (e.g. 5 means day runs 5am->5am)",
    )
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
    parser.add_argument("--decision-log", type=str, default=None, help="Path to decision log CSV")
    parser.add_argument("--log-dir", type=str, default=r"vm_logs\market_logs", help="Directory containing market logs")
    parser.add_argument("--famine-days", type=int, default=0, help="Consecutive losing days before pausing trading")
    parser.add_argument("--abundance-days", type=int, default=0, help="Consecutive winning days before resuming trading")
    parser.add_argument("--famine-daily-pct", type=float, default=0.0, help="Daily pct <= threshold counts as famine")
    parser.add_argument("--abundance-daily-pct", type=float, default=0.0, help="Daily pct >= threshold counts as abundance")
    parser.add_argument(
        "--resume-restart-mode",
        type=str,
        default="off",
        choices=["off", "intraday", "eod"],
        help="Resume from famine using a shadow restart sim (intraday or end-of-day)",
    )
    parser.add_argument(
        "--resume-restart-pct",
        type=float,
        default=0.0,
        help="Restart ROI threshold (%) required to resume when using resume-restart-mode",
    )
    parser.add_argument(
        "--fill-prob-per-min",
        type=float,
        default=0.0,
        help="Probability of passive fill per minute (0.0 to 1.0)",
    )
    args = parser.parse_args()

    os.environ["BT_VERBOSE"] = "1" if args.verbose else "0"

    def log(message: str) -> None:
        if not args.quiet:
            print(message)

    log(f"Running Unified Backtest (Shadow Mode) - Strategy: {args.strategy}...")

    log_dir = args.log_dir
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_ts = datetime.strptime(args.start_ts, "%Y-%m-%d %H:%M:%S")
    end_ts = datetime.strptime(args.end_ts, "%Y-%m-%d %H:%M:%S")
    warmup_start_ts = start_ts - timedelta(hours=args.warmup_hours)

    initial_cash = args.initial_cash
    min_requote_interval = args.min_requote_interval

    if ":" in args.strategy:
        # Dynamic loading: module:function
        import importlib
        module_name, func_name = args.strategy.split(":")
        mod = importlib.import_module(module_name)
        strat_func = getattr(mod, func_name)
    else:
        # Legacy behavior
        import server_mirror.backtesting.strategies.v3_variants as v3_variants
        strat_func = getattr(v3_variants, args.strategy)

    if args.strategy_kwargs and args.strategy_kwargs != "{}":
        strategy_kwargs = json.loads(args.strategy_kwargs)
    elif args.strategy == "generic_v3":
        strategy_kwargs = {
            "risk_pct": 0.8,
            "max_notional_pct": 0.10,
            "margin_cents": 8.0,
            "tightness_percentile": 10,
            "scaling_factor": 2.0,
            "max_inventory": 150,
            "max_loss_pct": 0.03
        }
    else:
        strategy_kwargs = {}

    print(f"DEBUG_STRAT_ARGS: {args.strategy} strategy_kwargs={strategy_kwargs}")

    def _build_strategy():
        try:
            strat = strat_func(**strategy_kwargs)
        except TypeError:
            strat = strat_func()

        if args.max_loss_pct is not None:
            try:
                if hasattr(strat, "mm") and hasattr(strat.mm, "max_loss_pct"):
                    strat.mm.max_loss_pct = float(args.max_loss_pct)
                if hasattr(strat, "max_loss_pct"):
                    strat.max_loss_pct = float(args.max_loss_pct)
            except (TypeError, ValueError):
                pass

        if args.trade_all_day:
            log("Disabling time constraints (trade-all-day)...")
            strat.active_hours = list(range(24))
        return strat

    strategy = _build_strategy()

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
        fill_prob_per_min=args.fill_prob_per_min,
    )

    # Seed initial prices from snapshot cost basis to avoid equity spikes
    for ticker, pos in initial_positions.items():
        yes_qty = int(pos.get("yes") or 0)
        no_qty = int(pos.get("no") or 0)
        cost = float(pos.get("cost") or 0.0)
        
        if yes_qty > 0:
            # Price in cents
            adapter.last_prices[ticker] = (cost / yes_qty) * 100.0
        elif no_qty > 0:
            # Price in cents (implied YES price)
            adapter.last_prices[ticker] = 100.0 - ((cost / no_qty) * 100.0)

    decision_log_path = args.decision_log
    decision_log = None
    if decision_log_path:
        decision_log = _build_decision_logger(decision_log_path)

    engine = UnifiedEngine(
        strategy=strategy,
        adapter=adapter,
        min_requote_interval=min_requote_interval,
        diag_log=None,
        decision_log=decision_log,
    )

    famine_enabled = args.famine_days > 0 and args.abundance_days > 0
    resume_on_restart = args.resume_restart_mode != "off"
    gate_state = {
        "enabled": True,
        "current_day": None,
        "day_start_equity": None,
        "last_day_equity": None,
        "neg_streak": 0,
        "pos_streak": 0,
    }
    shadow_state = {
        "day": None,
        "start_equity": None,
        "last_equity": None,
        "adapter": None,
        "engine": None,
    }

    if famine_enabled:
        class _GatedStrategy:
            def __init__(self, base, gate):
                self._base = base
                self._gate = gate
                self.name = getattr(base, "name", "gated")

            def __getattr__(self, item):
                return getattr(self._base, item)

            def on_market_update(self, *args, **kwargs):
                if not self._gate["enabled"]:
                    return []
                return self._base.on_market_update(*args, **kwargs)

        strategy = _GatedStrategy(strategy, gate_state)
        engine.strategy = strategy

    log(f"Loading ticks from {log_dir}...")
    ticks = list(iter_ticks_from_market_logs(log_dir))
    log(f"Loaded {len(ticks)} ticks.")
    if args.end_ts == default_end_ts and ticks:
        # If the user did not set an end bound, align to last available tick for accurate progress/ETA.
        last_tick_ts = max(tick["time"] for tick in ticks if tick.get("time"))
        if last_tick_ts < end_ts:
            end_ts = last_tick_ts
            log(f"Auto end_ts set to last tick: {end_ts}")

    log(f"Starting Warmup from {warmup_start_ts} to {start_ts}...")
    log(f"Simulation Start: {start_ts}")

    count = 0
    warmup_count = 0
    sim_start_perf_time = time_module.perf_counter()
    equity_history = []
    equity_breakdowns = []
    last_breakdown_date = None
    started = False

    def record_equity(record_ts: datetime) -> float:
        nonlocal last_breakdown_date
        cash_val = adapter.get_cash()
        holdings_val = _compute_holdings(adapter)
        equity_val = cash_val + holdings_val
        equity_history.append(
            {
                "date": record_ts.isoformat(),
                "equity": equity_val,
                "cash": cash_val,
                "holdings": holdings_val,
            }
        )
        # Record breakdown once per day (on the first tick of each day)
        current_date = record_ts.date()
        if last_breakdown_date is None or current_date > last_breakdown_date:
            positions = adapter.get_positions()
            for ticker, pos in positions.items():
                yes_qty = int(pos.get("yes") or 0)
                no_qty = int(pos.get("no") or 0)
                last_price = adapter.last_prices.get(ticker, 50.0)
                value = (yes_qty * (last_price / 100.0)) + (no_qty * ((100.0 - last_price) / 100.0))
                equity_breakdowns.append(
                    {
                        "date": current_date.isoformat(),
                        "ticker": ticker,
                        "yes_qty": yes_qty,
                        "no_qty": no_qty,
                        "last_price": last_price,
                        "value": value,
                        "cash": cash_val,
                        "equity": equity_val,
                    }
                )
            last_breakdown_date = current_date
        return equity_val

    settled_dates: set[tuple[str, datetime.date]] = set()

    # Look-forward seeder for tickers missing from warmup
    # Find the first index where t >= start_ts
    start_idx = 0
    for i, tick in enumerate(ticks):
        if tick["time"] >= start_ts:
            start_idx = i
            break
    
    missing_tickers = [t for t in initial_positions if t not in adapter.last_prices]
    if missing_tickers:
        log(f"Looking forward for {len(missing_tickers)} missing ticker prices...")
        for ticker in missing_tickers:
            # Search forward from start_idx
            for i in range(start_idx, len(ticks)):
                if ticks[i]["ticker"] == ticker:
                    ms = ticks[i]["market_state"]
                    ya = ms.get("yes_ask")
                    yb = ms.get("yes_bid")
                    price = None
                    if ya is not None and yb is not None:
                        price = (float(ya) + float(yb)) / 2.0
                    elif ya is not None:
                        price = float(ya)
                    elif yb is not None:
                        price = float(yb)
                    
                    if price is not None:
                        adapter.last_prices[ticker] = price
                        log(f"  Found forward price for {ticker}: {price}")
                        break

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

            adapter.process_tick(tick["ticker"], tick["market_state"], t)

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
            started = True
        
        equity_val = record_equity(t)

        if famine_enabled:
            if args.day_boundary_hour:
                day = (t - timedelta(hours=args.day_boundary_hour)).date()
            else:
                day = t.date()
            if gate_state["current_day"] is None:
                gate_state["current_day"] = day
                gate_state["day_start_equity"] = equity_val
                gate_state["last_day_equity"] = equity_val
            elif day == gate_state["current_day"]:
                gate_state["last_day_equity"] = equity_val
            else:
                # Day rolled over: evaluate previous day performance
                start_eq = gate_state["day_start_equity"]
                end_eq = gate_state["last_day_equity"]
                if start_eq and end_eq is not None:
                    daily_pct = ((end_eq / start_eq) - 1.0) * 100.0
                    if daily_pct <= args.famine_daily_pct:
                        gate_state["neg_streak"] += 1
                        gate_state["pos_streak"] = 0
                    elif daily_pct >= args.abundance_daily_pct:
                        gate_state["pos_streak"] += 1
                        gate_state["neg_streak"] = 0
                    else:
                        gate_state["neg_streak"] = 0
                        gate_state["pos_streak"] = 0

                if gate_state["enabled"] and gate_state["neg_streak"] >= args.famine_days:
                    gate_state["enabled"] = False
                    if not args.quiet:
                        print(f"[FAMINE] Pausing at {t} after {gate_state['neg_streak']} losing days")
                    for order in list(adapter.open_orders):
                        adapter.cancel_order(order.get("order_id"))
                elif (not gate_state["enabled"]) and (not resume_on_restart) and gate_state["pos_streak"] >= args.abundance_days:
                    gate_state["enabled"] = True
                    if not args.quiet:
                        print(f"[ABUNDANCE] Resuming at {t} after {gate_state['pos_streak']} winning days")
                    gate_state["neg_streak"] = 0
                    gate_state["pos_streak"] = 0

                if resume_on_restart and not gate_state["enabled"] and args.resume_restart_mode == "eod":
                    start_eq = shadow_state["start_equity"]
                    end_eq = shadow_state["last_equity"]
                    if start_eq and end_eq is not None:
                        restart_pct = ((end_eq / start_eq) - 1.0) * 100.0
                        if restart_pct >= args.resume_restart_pct:
                            gate_state["enabled"] = True
                            gate_state["neg_streak"] = 0
                            gate_state["pos_streak"] = 0
                            if not args.quiet:
                                print(
                                    f"[RESTART] Resuming at {t} (EOD restart ROI {restart_pct:.2f}%)"
                                )

                gate_state["current_day"] = day
                gate_state["day_start_equity"] = equity_val
                gate_state["last_day_equity"] = equity_val
                if resume_on_restart and not gate_state["enabled"]:
                    shadow_state["day"] = day
                    shadow_state["start_equity"] = adapter.get_cash()
                    shadow_state["last_equity"] = shadow_state["start_equity"]
                    shadow_adapter = SimAdapter(initial_cash=shadow_state["start_equity"])
                    shadow_engine = UnifiedEngine(
                        strategy=_build_strategy(),
                        adapter=shadow_adapter,
                        min_requote_interval=min_requote_interval,
                        diag_log=None,
                        decision_log=None,
                    )
                    shadow_state["adapter"] = shadow_adapter
                    shadow_state["engine"] = shadow_engine
                else:
                    shadow_state["day"] = None
                    shadow_state["start_equity"] = None
                    shadow_state["last_equity"] = None
                    shadow_state["adapter"] = None
                    shadow_state["engine"] = None

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

        if resume_on_restart and not gate_state["enabled"]:
            shadow_engine = shadow_state.get("engine")
            shadow_adapter = shadow_state.get("adapter")
            if shadow_engine is not None and shadow_adapter is not None:
                shadow_engine.on_tick(
                    ticker=tick["ticker"],
                    market_state=tick["market_state"],
                    current_time=t,
                    tick_seq=tick.get("seq"),
                    tick_source=tick.get("source_file"),
                    tick_row=tick.get("source_row"),
                )
                shadow_equity = shadow_adapter.get_cash() + _compute_holdings(shadow_adapter)
                shadow_state["last_equity"] = shadow_equity
                if args.resume_restart_mode == "intraday":
                    start_eq = shadow_state["start_equity"]
                    if start_eq and ((shadow_equity / start_eq) - 1.0) * 100.0 >= args.resume_restart_pct:
                        gate_state["enabled"] = True
                        gate_state["neg_streak"] = 0
                        gate_state["pos_streak"] = 0
                        shadow_state["day"] = None
                        shadow_state["start_equity"] = None
                        shadow_state["last_equity"] = None
                        shadow_state["adapter"] = None
                        shadow_state["engine"] = None
                        if not args.quiet:
                            print(
                                f"[RESTART] Resuming at {t} (intraday restart ROI >= {args.resume_restart_pct:.2f}%)"
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
    if equity_history:
        equity_df = pd.DataFrame(equity_history)
        equity_df.to_csv(out_dir / "equity_history.csv", index=False)
    if equity_breakdowns:
        breakdown_df = pd.DataFrame(equity_breakdowns)
        breakdown_df.to_csv(out_dir / "equity_breakdown.csv", index=False)
    log(f"\nSaved trades to {out_dir / 'unified_trades.csv'}")


if __name__ == "__main__":
    main()
