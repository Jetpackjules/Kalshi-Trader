import json
import os
import sys
import argparse

# Allow running as a script from junk/ while importing repo packages.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from collections import defaultdict
from datetime import datetime

from backtesting.engine import ComplexBacktester


def load_factory(spec: str):
    if ":" not in spec:
        raise ValueError("Strategy spec must be module:symbol")
    mod_name, sym = spec.split(":", 1)
    import importlib

    mod = importlib.import_module(mod_name)
    factory = getattr(mod, sym)
    if not callable(factory):
        raise TypeError(f"{spec} is not callable")
    return factory


def parse_snapshot_timestamp(snapshot: dict) -> datetime:
    # best-effort compatibility with runner._parse_snapshot_timestamp
    for k in ("timestamp", "snapshot_time", "created_at"):
        if k in snapshot and snapshot[k]:
            v = str(snapshot[k])
            try:
                return datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    return datetime.fromisoformat(v)
                except ValueError:
                    pass

    # fallback: filename-style keys sometimes present
    if "snapshot_name" in snapshot and snapshot["snapshot_name"]:
        v = str(snapshot["snapshot_name"])
        # e.g. snapshot_2026-01-04_081048
        if "snapshot_" in v:
            v = v.split("snapshot_", 1)[1]
        for fmt in ("%Y-%m-%d_%H%M%S", "%Y-%m-%d_%H%M%S.json"):
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                continue

    raise ValueError("Could not parse snapshot timestamp")


def main():
    parser = argparse.ArgumentParser(description="Count backtest 'submissions' (strategy non-empty returns) in a time window.")
    parser.add_argument(
        "--snapshot",
        default=r"server_mirror\snapshot_2026-01-04_081622.json",
        help="Snapshot JSON path used to seed portfolio + define start timestamp.",
    )
    parser.add_argument(
        "--log-dir",
        default=r"vm_logs\market_logs",
        help="Directory containing market_data_*.csv tick logs.",
    )
    parser.add_argument(
        "--cap-log",
        default="market_data_KXHIGHNY-26JAN04.csv",
        help="CSV filename under --log-dir used to cap end time (latest tick).",
    )
    parser.add_argument(
        "--strategy",
        default="backtesting.strategies.v3_variants:baseline_v3",
        help="Strategy factory spec: module:symbol (e.g. backtesting.strategies.v3_variants:hb_notional_010)",
    )
    args = parser.parse_args()

    snapshot_path = args.snapshot
    log_dir = args.log_dir
    strategy_spec = args.strategy

    # Cap the run to the latest available tick in the relevant log.
    # This makes the replay window align with what the live trader could have seen.
    cap_log_path = os.path.join(log_dir, args.cap_log)
    end_dt = None
    try:
        with open(cap_log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            # Read last ~8KB to find final line.
            f.seek(max(0, size - 8192))
            tail = f.read().decode("utf-8", errors="ignore")
        last_line = [ln for ln in tail.splitlines() if ln.strip()][-1]
        last_ts = last_line.split(",", 1)[0]
        end_dt = datetime.fromisoformat(last_ts)
    except Exception:
        end_dt = None

    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    start_dt = parse_snapshot_timestamp(snapshot)
    base_capital = float(snapshot.get("daily_start_equity") or 0.0) or float(
        snapshot.get("balance") or snapshot.get("cash") or 1000.0
    )

    factory = load_factory(strategy_spec)
    strat = factory()

    counters = defaultdict(int)
    original = strat.on_market_update

    def wrapped_on_market_update(*args, **kwargs):
        # Expected signature: (ticker, market_state, current_time, inventories, active_orders, cash, idx)
        current_time = None
        if len(args) >= 3:
            current_time = args[2]

        res = original(*args, **kwargs)
        if res is None:
            return res

        counters["strategy_returns_not_none"] += 1

        # Exclude pre-start warmup seeding ticks: engine ignores these for trading.
        in_window = True
        if current_time is not None:
            if current_time < start_dt:
                in_window = False
            if end_dt is not None and current_time > end_dt:
                in_window = False

        if not in_window:
            counters["returns_outside_window"] += 1
            if isinstance(res, list) and len(res) > 0:
                counters["non_empty_outside_window"] += 1
            return res

        counters["returns_in_window"] += 1
        if isinstance(res, list) and len(res) > 0:
            counters["strategy_returns_non_empty"] += 1
            counters["orders_returned"] += len(res)
            counters["qty_returned"] += sum(int(o.get("qty", 0) or 0) for o in res)
            for o in res:
                counters[f"by_action_{o.get('action')}"] += 1
        return res

    strat.on_market_update = wrapped_on_market_update

    bt = ComplexBacktester(
        strategies=[strat],
        log_dir=log_dir,
        charts_dir="backtest_charts",
        start_datetime=start_dt,
        end_datetime=end_dt,
        start_date=start_dt.strftime("%y%b%d").upper(),
        end_date="",
        seed_warmup_from_history=True,
        round_prices_to_int=True,
        min_requote_interval_seconds=2.0,
        initial_capital=base_capital,
        generate_daily_charts=False,
        generate_final_chart=False,
    )

    # seed portfolio from snapshot (minimal: daily_start_equity + cash + positions)
    p = bt.portfolios[strat.name]
    p["daily_start_equity"] = float(snapshot.get("daily_start_equity") or base_capital)
    p["wallet"].available_cash = float(snapshot.get("cash") or snapshot.get("balance") or base_capital)

    positions = snapshot.get("positions") or {}
    for ticker, pos in positions.items():
        yes = int(pos.get("yes", 0) or 0)
        no = int(pos.get("no", 0) or 0)
        cost = float(pos.get("cost", 0.0) or 0.0)
        if yes:
            p["inventory_yes"]["MM"][ticker] += yes
        if no:
            p["inventory_no"]["MM"][ticker] += no
        if cost:
            p["cost_basis"][ticker] += cost

    bt.run()

    trades = bt.portfolios[strat.name]["trades"]

    print("=== Backtest submission counts (strategy return-based) ===")
    print(f"strategy_returns_not_none: {counters['strategy_returns_not_none']}")
    print(f"returns_in_window: {counters['returns_in_window']}")
    print(f"returns_outside_window: {counters['returns_outside_window']}")
    print(f"non_empty_outside_window: {counters['non_empty_outside_window']}")
    print(f"strategy_returns_non_empty: {counters['strategy_returns_non_empty']}")
    print(f"orders_returned: {counters['orders_returned']}")
    print(f"qty_returned: {counters['qty_returned']}")
    for k in sorted([k for k in counters.keys() if k.startswith('by_action_')]):
        print(f"{k}: {counters[k]}")

    print("=== Backtest trade (fill) counts ===")
    print(f"trades_len: {len(trades)}")


if __name__ == "__main__":
    main()
