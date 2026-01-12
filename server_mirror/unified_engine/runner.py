from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from unified_engine.adapters import SimAdapter
from unified_engine.engine import UnifiedEngine
from unified_engine.tick_sources import iter_ticks_from_live_log, iter_ticks_from_market_logs


def _load_strategy(spec: str):
    if ":" not in spec:
        raise ValueError("Strategy must be module:symbol")
    module, symbol = spec.split(":", 1)
    mod = importlib.import_module(module)
    factory = getattr(mod, symbol)
    if not callable(factory):
        raise TypeError(f"{spec} is not callable")
    return factory()


def _seed_from_snapshot(adapter: SimAdapter, strategy, snapshot_path: str) -> float:
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snap = json.load(f)

    daily_start_equity = float(snap.get("daily_start_equity") or 0.0)
    balance = float(snap.get("balance") or snap.get("cash") or 0.0)
    base_cash = daily_start_equity if daily_start_equity > 0 else balance

    adapter.cash = balance
    adapter.positions = {}
    positions = snap.get("positions") or {}
    for ticker, pos in positions.items():
        adapter.positions[ticker] = {
            "yes": int(pos.get("yes") or 0),
            "no": int(pos.get("no") or 0),
            "cost": float(pos.get("cost") or 0.0),
        }

    cfg = snap.get("strategy_config") or {}
    if hasattr(strategy, "risk_pct") and "risk_pct" in cfg:
        strategy.risk_pct = float(cfg["risk_pct"])
    if hasattr(strategy, "tightness_percentile") and "tightness_percentile" in cfg:
        strategy.tightness_percentile = int(cfg["tightness_percentile"])

    return base_cash


def _filter_ticks(
    ticks: Iterable[dict], start_ts: datetime | None, end_ts: datetime | None
) -> Iterable[dict]:
    for tick in ticks:
        if start_ts and tick["time"] < start_ts:
            if "KXHIGHNY-26JAN09-B49.5" in tick['ticker'] and "05:05:26" in str(tick['time']):
                print(f"DEBUG: DROPPED TICK (before start): {tick['time']} < {start_ts}")
            continue
        if end_ts and tick["time"] > end_ts:
            if "KXHIGHNY-26JAN09-B49.5" in tick['ticker'] and "05:05:26" in str(tick['time']):
                print(f"DEBUG: DROPPED TICK (after end): {tick['time']} > {end_ts}")
            break
        yield tick


def _build_diag_logger(enabled: bool):
    if not enabled:
        return None

    def _log(event: str, *, tick_ts: datetime | None = None, **fields) -> None:
        log_ts = datetime.now().isoformat()
        tick_value = tick_ts.isoformat() if tick_ts else "NONE"
        parts = [f"event={event}", f"log_ts={log_ts}", f"tick_ts={tick_value}"]
        for key, value in fields.items():
            parts.append(f"{key}={value}")
        print("[DIAG] " + " ".join(parts))

    return _log


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
    file_exists = os.path.isfile(path)
    handle = open(path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    if not file_exists:
        writer.writeheader()
        handle.flush()

    def _log(row: dict) -> None:
        record = {k: "" for k in fieldnames}
        record.update(row)
        writer.writerow(record)
        handle.flush()

    return _log


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified engine prototype runner.")
    parser.add_argument("--strategy", default="backtesting.strategies.v3_variants:hb_notional_010")
    parser.add_argument("--log-dir", default=os.path.join("vm_logs", "market_logs"))
    parser.add_argument("--tick-log", default="", help="Optional live tick CSV (live_ticks_*.csv)")
    parser.add_argument("--use-ingest", action="store_true", help="Use ingest_timestamp from live tick logs")
    parser.add_argument("--follow", action="store_true", help="Follow live tick log for new rows")
    parser.add_argument("--snapshot", default="", help="Optional snapshot JSON for starting state")
    parser.add_argument("--initial-cash", type=float, default=100.0)
    parser.add_argument("--min-requote-interval", type=float, default=2.0)
    parser.add_argument("--start-ts", default="", help="YYYY-mm-dd HH:MM:SS[.fff]")
    parser.add_argument("--end-ts", default="", help="YYYY-mm-dd HH:MM:SS[.fff]")
    parser.add_argument("--out-dir", default="unified_engine_out")
    parser.add_argument("--decision-log", default="", help="CSV path for decision intents (blank = out_dir/decision_intents.csv)")
    parser.add_argument("--diag-log", action="store_true", help="Emit per-tick diagnostic lines")
    parser.add_argument("--diag-every", type=int, default=1, help="Ticks between diagnostics")
    parser.add_argument("--diag-heartbeat-s", type=float, default=30.0, help="Seconds between follow heartbeats")
    parser.add_argument("--status-every-ticks", type=int, default=1, help="Write status every N ticks")
    parser.add_argument("--live", action="store_true", help="Run in LIVE trading mode (real money)")
    parser.add_argument("--key-file", default="kalshi_prod_private_key.pem", help="Path to private key for live trading")
    parser.add_argument("--fill-latency-s", type=float, default=0.0, help="Constant fill latency for sim fills")
    parser.add_argument("--fill-latency-model", default="", help="Latency model JSON with delays_seconds/clamped_delays")
    parser.add_argument("--fill-latency-seed", type=int, default=0, help="Seed for latency sampling")
    args = parser.parse_args()

    diag_log = _build_diag_logger(args.diag_log)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    decision_log_path = args.decision_log or os.path.join(args.out_dir, "decision_intents.csv")
    print(f"Decision log: {decision_log_path}")
    decision_log = _build_decision_logger(decision_log_path)

    strategy = _load_strategy(args.strategy)
    try:
        import sys
        print(f"DEBUG: backtesting.engine imported from: {sys.modules['backtesting.engine'].__file__}")
    except:
        print("DEBUG: Could not print backtesting.engine location")

    latency_sampler = None
    fill_latency_s = float(args.fill_latency_s)
    if args.fill_latency_model:
        with open(args.fill_latency_model, "r", encoding="utf-8") as f:
            model = json.load(f)
        delays = (
            model.get("clamped_delays")
            or model.get("delays_seconds")
            or model.get("matched_delays")
            or []
        )
        if not delays:
            raise ValueError(f"No delays found in latency model: {args.fill_latency_model}")
        rng = random.Random(args.fill_latency_seed)
        latency_sampler = lambda: rng.choice(delays)

    if args.live:
        from unified_engine.adapters import LiveAdapter
        print("!!! WARNING: RUNNING IN LIVE TRADING MODE !!!")
        adapter = LiveAdapter(key_path=args.key_file, diag_log=diag_log)
        
        # --- SNAPSHOT ON LAUNCH ---
        try:
            snapshot_dir = os.path.expanduser("~/snapshots")
            os.makedirs(snapshot_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            snapshot_file = os.path.join(snapshot_dir, f"snapshot_{timestamp}.json")
            
            # Sync state to ensure we have latest data
            cash = adapter.get_cash()
            positions = adapter.get_positions()
            portfolio_val = getattr(adapter, "get_portfolio_value", lambda: 0.0)()
            equity = cash + portfolio_val
            
            snapshot_data = {
                "timestamp": timestamp,
                "daily_start_equity": equity, # Use Total Equity, not just Cash
                "balance": cash,
                "positions": positions,
                "strategy_config": {
                    "name": strategy.name,
                    "risk_pct": getattr(strategy, "risk_pct", 0.5)
                }
            }
            
            with open(snapshot_file, "w") as f:
                json.dump(snapshot_data, f, indent=2)
            print(f"Saved launch snapshot to: {snapshot_file}")
        except Exception as e:
            print(f"Failed to save launch snapshot: {e}")
            
    else:
        adapter = SimAdapter(
            initial_cash=float(args.initial_cash),
            diag_log=diag_log,
            fill_latency_s=fill_latency_s,
            fill_latency_sampler=latency_sampler,
        )

    if args.snapshot:
        _seed_from_snapshot(adapter, strategy, args.snapshot)

    if args.tick_log:
        ticks = iter_ticks_from_live_log(
            args.tick_log,
            use_ingest=args.use_ingest,
            follow=args.follow,
            diag_log=diag_log,
            heartbeat_s=args.diag_heartbeat_s,
        )
    else:
        print(f"DEBUG: iter_ticks_from_market_logs imported from: {iter_ticks_from_market_logs.__module__}")
        print(f"DEBUG: Using log_dir: {args.log_dir}")
        ticks = iter_ticks_from_market_logs(
            args.log_dir,
            follow=args.follow,
            diag_log=diag_log,
            heartbeat_s=args.diag_heartbeat_s,
        )

    start_ts = None
    if args.start_ts:
        start_raw = args.start_ts.replace("T", " ").replace("_", " ")
        try:
            start_ts = datetime.strptime(start_raw, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            start_ts = datetime.strptime(start_raw, "%Y-%m-%d %H:%M:%S")

    end_ts = None
    if args.end_ts:
        end_raw = args.end_ts.replace("T", " ").replace("_", " ")
        try:
            end_ts = datetime.strptime(end_raw, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            end_ts = datetime.strptime(end_raw, "%Y-%m-%d %H:%M:%S")

    filtered_ticks = _filter_ticks(ticks, start_ts, end_ts)

    engine = UnifiedEngine(
        strategy=strategy,
        adapter=adapter,
        min_requote_interval=args.min_requote_interval,
        diag_log=diag_log,
        diag_every=args.diag_every,
        decision_log=decision_log,
    )

    out_dir = Path(args.out_dir)

    # Initialize daily start equity
    daily_start_equity = 0.0
    try:
        # Try to load from snapshot if available
        snapshot_dir = os.path.expanduser("~/snapshots")
        if os.path.exists(snapshot_dir):
            snapshots = sorted([f for f in os.listdir(snapshot_dir) if f.startswith("snapshot_")])
            if snapshots:
                latest = os.path.join(snapshot_dir, snapshots[-1])
                with open(latest, "r") as f:
                    data = json.load(f)
                    # Only use if from today
                    if data.get("timestamp", "").startswith(datetime.now().strftime("%Y-%m-%d")):
                        daily_start_equity = data.get("daily_start_equity", 0.0)
    except Exception:
        pass
        
    if daily_start_equity == 0.0:
        daily_start_equity = adapter.get_cash() + getattr(adapter, "get_portfolio_value", lambda: 0.0)()

    def _write_status():
        # 1. Trades
        trades_df = pd.DataFrame(adapter.trades)
        trades_df.to_csv(out_dir / "trades.csv", index=False)
        
        # 2. Positions
        positions_out = {k: v for k, v in adapter.get_positions().items() if (v.get("yes") or 0) > 0 or (v.get("no") or 0) > 0}
        with open(out_dir / "unified_positions.json", "w", encoding="utf-8") as f:
            json.dump({"cash": adapter.get_cash(), "positions": positions_out}, f, indent=2)

        # 3. Dashboard Compatibility (trader_status.json)
        try:
            cash = adapter.get_cash()
            portfolio_val = getattr(adapter, "get_portfolio_value", lambda: 0.0)()
            equity = cash + portfolio_val
            risk_pct = getattr(strategy, "risk_pct", 0.5)
            budget = daily_start_equity * risk_pct
            
            # Calculate exposure (sum of cost of positions)
            exposure = sum(p.get("cost", 0.0) for p in positions_out.values())
            
            # --- Trading Window Logic ---
            def get_window_status():
                now = datetime.now()
                h = now.hour
                # Windows: 5-8, 13-17, 21-23
                windows = [(5, 8), (13, 17), (21, 23)]
                
                is_open = False
                current_window = None
                
                for start, end in windows:
                    if start <= h <= end:
                        is_open = True
                        current_window = (start, end)
                        break
                        
                if is_open:
                    # Time until close (end of the 'end' hour)
                    target_hour = current_window[1] + 1
                    if target_hour >= 24:
                         target = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                    else:
                         target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
                    diff = target - now
                    # Format HH:MM:SS
                    s = int(diff.total_seconds())
                    return {
                        "state": "OPEN",
                        "message": f"Closes in {s//3600:02}:{(s%3600)//60:02}:{s%60:02}",
                        "color": "#10B981" # Green
                    }
                else:
                    # Time until next open
                    next_start = None
                    for start, end in windows:
                        if start > h:
                            next_start = start
                            break
                    
                    if next_start is not None:
                        target = now.replace(hour=next_start, minute=0, second=0, microsecond=0)
                    else:
                        # Next day first window
                        target = now.replace(hour=windows[0][0], minute=0, second=0, microsecond=0) + timedelta(days=1)
                        
                    diff = target - now
                    s = int(diff.total_seconds())
                    return {
                        "state": "CLOSED",
                        "message": f"Opens in {s//3600:02}:{(s%3600)//60:02}:{s%60:02}",
                        "color": "#EF4444" # Red
                    }
            
            window_status = get_window_status()
            # ---------------------------

            status_data = {
                "status": "RUNNING",
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "strategy": getattr(strategy, "name", "UnifiedStrategy"),
                "equity": equity,
                "cash": cash,
                "portfolio_value": portfolio_val,
                "pnl_today": equity - daily_start_equity,
                "trades_today": len(adapter.trades),
                "daily_budget": budget,
                "daily_start_equity": daily_start_equity,
                "current_exposure": exposure,
                "spent_today": exposure, # Approx
                "spent_pct": (exposure / budget * 100) if budget > 0 else 0.0,
                "positions": positions_out,
                "target_date": "Unified",
                "last_decision": getattr(strategy, "last_decision", {}),
                "window_status": window_status
            }
            with open("trader_status.json", "w") as f:
                json.dump(status_data, f)
            
            # Print to stdout for log parsing (compatibility with generate_live_vs_backtest_graph.py)
            now = datetime.now()
            print(f"--- Status @ {now.strftime('%H:%M:%S.%f')[:-3]} ---")
            print(f"Equity: ${equity:.2f}")
            print(f"Cash: ${cash:.2f}")
            print(f"Portfolio Value: ${portfolio_val:.2f}")
            print(f"Daily Budget: ${budget:.2f}")
            print(f"Exposure: ${exposure:.2f}")
            
        except Exception as e:
            print(f"Failed to write trader_status.json: {e}")

    status_every_ticks = max(1, int(args.status_every_ticks))
    # Run loop with periodic updates
    count = 0
    for tick in filtered_ticks:
        if "KXHIGHNY-26JAN09-B49.5" in tick['ticker'] and "05:05:26" in str(tick['time']):
            print(f"DEBUG: LOOP TICK: {tick['time']}")
        count += 1
        if diag_log and (count % args.diag_every == 0):
            diag_log("TICK_IN", tick_ts=tick["time"], ticker=tick["ticker"])
        
        engine.on_tick(
            ticker=tick["ticker"],
            market_state=tick["market_state"],
            current_time=tick["time"],
            tick_seq=tick.get("seq"),
            tick_source=tick.get("source_file"),
            tick_row=tick.get("source_row"),
        )
        
        # Update status frequently to keep dashboard fresh
        if count % status_every_ticks == 0:
            _write_status()

    # Final write
    _write_status()
    
    orders_df = pd.DataFrame(adapter.order_history)
    orders_df.to_csv(out_dir / "unified_orders.csv", index=False)

    print("Wrote:", out_dir / "unified_trades.csv")
    print("Wrote:", out_dir / "unified_orders.csv")
    print("Wrote:", out_dir / "unified_positions.json")
    return 0


if __name__ == "__main__":
    import sys
    sys.path.append(os.getcwd()) # Ensure current directory is in path for module imports
    raise SystemExit(main())
