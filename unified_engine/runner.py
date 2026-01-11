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
            continue
        if end_ts and tick["time"] > end_ts:
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
        "reason",
        "edge",
        "edge_yes",
        "edge_no",
        "fair_prob",
        "mid",
        "edge_cents",
        "required",
        "fee_cents",
        "margin",
        "edge_after_fee_real",
        "edge_after_fee",
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
    parser.add_argument("--fill-latency-s", type=float, default=0.0, help="Constant fill latency for sim fills")
    parser.add_argument("--fill-latency-model", default="", help="Latency model JSON with delays_seconds/clamped_delays")
    parser.add_argument("--fill-latency-seed", type=int, default=0, help="Seed for latency sampling")
    args = parser.parse_args()

    diag_log = _build_diag_logger(args.diag_log)

    strategy = _load_strategy(args.strategy)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    decision_log_path = args.decision_log or os.path.join(args.out_dir, "decision_intents.csv")
    print(f"Decision log: {decision_log_path}")
    decision_log = _build_decision_logger(decision_log_path)

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

    adapter = SimAdapter(
        initial_cash=float(args.initial_cash),
        diag_log=diag_log,
        out_dir=args.out_dir,
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
    engine.run(filtered_ticks)

    out_dir = Path(args.out_dir)

    trades_df = pd.DataFrame(adapter.trades)
    trades_df.to_csv(out_dir / "unified_trades.csv", index=False)

    orders_df = pd.DataFrame(adapter.order_history)
    orders_df.to_csv(out_dir / "unified_orders.csv", index=False)

    positions_out = {k: v for k, v in adapter.positions.items() if (v.get("yes") or 0) > 0 or (v.get("no") or 0) > 0}
    with open(out_dir / "unified_positions.json", "w", encoding="utf-8") as f:
        json.dump(
            {"cash": adapter.cash, "positions": positions_out},
            f,
            indent=2,
        )

    print("Wrote:", out_dir / "unified_trades.csv")
    print("Wrote:", out_dir / "unified_orders.csv")
    print("Wrote:", out_dir / "unified_positions.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
