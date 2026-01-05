import argparse
import csv
import json
import os
from collections import deque
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go

import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from backtesting.engine import ComplexBacktester
from backtesting.runner import _parse_snapshot_timestamp, _seed_portfolio_from_snapshot
from backtesting.strategies.v3_variants import hb_notional_010


def _parse_last_timestamp(csv_path: str) -> datetime | None:
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            tail = deque(f, maxlen=2)
        if not tail:
            return None
        last_line = tail[-1].strip()
        if not last_line:
            return None
        if last_line.startswith("timestamp,"):
            return None
        ts_str = last_line.split(",", 1)[0]
        return pd.to_datetime(ts_str).to_pydatetime()
    except Exception:
        return None


def _find_latest_market_timestamp(log_dir: str) -> datetime:
    latest = None
    for name in os.listdir(log_dir):
        if not name.startswith("market_data_") or not name.endswith(".csv"):
            continue
        ts = _parse_last_timestamp(os.path.join(log_dir, name))
        if ts is None:
            continue
        if latest is None or ts > latest:
            latest = ts
    if latest is None:
        raise RuntimeError(f"No market_data_*.csv files with timestamps found in {log_dir}")
    return latest


def _load_snapshot(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_live_trades(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Live trades file not found: {path}")
    return pd.read_csv(path, parse_dates=["timestamp"])

def _load_live_events(fills_path: str, attempts_path: str) -> tuple[pd.DataFrame, str]:
    if os.path.exists(fills_path):
        fills = pd.read_csv(fills_path, parse_dates=["timestamp"])
        if not fills.empty:
            fills = fills.rename(columns={"timestamp": "time"}).copy()
            fills["price"] = pd.to_numeric(fills.get("avg_price_cents"), errors="coerce")
            fills["cost"] = pd.to_numeric(fills.get("cost_delta"), errors="coerce").abs()
            fills["fee"] = 0.0
            fills["source"] = "FILL"
            return fills, "fills.csv"

    if os.path.exists(attempts_path):
        attempts = pd.read_csv(attempts_path, parse_dates=["timestamp"])
        if not attempts.empty:
            attempts = attempts.rename(columns={"timestamp": "time"}).copy()
            attempts["action"] = attempts.get("side", "").astype(str).str.upper()
            attempts["price"] = pd.to_numeric(attempts.get("price"), errors="coerce")
            attempts["cost"] = 0.0
            attempts["fee"] = 0.0
            attempts["source"] = "ATTEMPT"
            return attempts, "attempted_orders.csv"

    return pd.DataFrame(columns=["time", "ticker", "action", "qty", "price", "cost", "fee", "source"]), "none"

def _load_attempts(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=["time", "ticker", "action", "qty", "price", "cost", "fee", "source"])
    attempts = pd.read_csv(path, parse_dates=["timestamp"])
    if attempts.empty:
        return pd.DataFrame(columns=["time", "ticker", "action", "qty", "price", "cost", "fee", "source"])
    attempts = attempts.rename(columns={"timestamp": "time"}).copy()
    attempts["action"] = attempts.get("side", "").astype(str).str.upper()
    attempts["price"] = pd.to_numeric(attempts.get("price"), errors="coerce")
    attempts["cost"] = 0.0
    attempts["fee"] = 0.0
    attempts["source"] = "ATTEMPT"
    return attempts


def _backtest_trades(snapshot: dict, log_dir: str, end_dt: datetime) -> pd.DataFrame:
    start_dt = _parse_snapshot_timestamp(snapshot)
    start_date = start_dt.strftime("%y%b%d").upper()

    strategy = hb_notional_010()
    cfg = snapshot.get("strategy_config") or {}
    if "risk_pct" in cfg and hasattr(strategy, "risk_pct"):
        strategy.risk_pct = float(cfg["risk_pct"])
    if "tightness_percentile" in cfg and hasattr(strategy, "tightness_percentile"):
        strategy.tightness_percentile = int(cfg["tightness_percentile"])

    base_capital = float(snapshot.get("daily_start_equity") or 0.0) or float(snapshot.get("balance") or 0.0)
    bt = ComplexBacktester(
        strategies=[strategy],
        log_dir=log_dir,
        charts_dir="backtest_charts",
        start_date=start_date,
        end_date="",
        start_datetime=start_dt,
        end_datetime=end_dt,
        generate_daily_charts=False,
        generate_final_chart=False,
        initial_capital=base_capital,
    )
    _seed_portfolio_from_snapshot(bt, strategy.name, snapshot)
    bt.run()

    trades = bt.portfolios[strategy.name]["trades"]
    if not trades:
        return pd.DataFrame(columns=["time", "ticker", "action", "price", "qty", "cost", "fee", "source"])

    return pd.DataFrame(trades)


def _summarize_trades(df: pd.DataFrame, label: str) -> dict:
    if df.empty:
        return {
            "label": label,
            "trades": 0,
            "qty": 0,
            "cost": 0.0,
            "fees": 0.0,
        }
    return {
        "label": label,
        "trades": int(len(df)),
        "qty": int(df["qty"].sum()),
        "cost": float(df["cost"].sum()),
        "fees": float(df.get("fee", pd.Series(dtype=float)).sum()),
    }


def _plot_cumulative_trades(backtest: pd.DataFrame, live: pd.DataFrame, out_path: str) -> None:
    fig = go.Figure()
    if not backtest.empty:
        backtest = backtest.sort_values("time")
        fig.add_trace(
            go.Scatter(
                x=backtest["time"],
                y=list(range(1, len(backtest) + 1)),
                mode="lines+markers",
                name="Backtest (hb_notional_010)",
            )
        )
    if not live.empty:
        live = live.sort_values("timestamp")
        fig.add_trace(
            go.Scatter(
                x=live["timestamp"],
                y=list(range(1, len(live) + 1)),
                mode="lines+markers",
                name="Live (trades.csv)",
            )
        )
    fig.update_layout(
        title="Cumulative Trade Count (Snapshot Window)",
        xaxis_title="Time",
        yaxis_title="Trades",
        hovermode="x unified",
        height=800,
    )
    fig.write_html(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare live trades vs backtest since snapshot.")
    parser.add_argument("--snapshot", required=True, help="Snapshot JSON path")
    parser.add_argument("--log-dir", default=os.path.join("vm_logs", "market_logs"))
    parser.add_argument("--live-trades", default=os.path.join("vm_logs", "trades.csv"))
    parser.add_argument("--live-fills", default=os.path.join("vm_logs", "fills.csv"))
    parser.add_argument("--live-attempts", default=os.path.join("vm_logs", "attempted_orders.csv"))
    parser.add_argument("--out-dir", default="backtest_charts")
    args = parser.parse_args()

    snapshot = _load_snapshot(args.snapshot)
    start_dt = _parse_snapshot_timestamp(snapshot)
    end_dt = _find_latest_market_timestamp(args.log_dir)

    os.makedirs(args.out_dir, exist_ok=True)

    live_source = "trades.csv"
    try:
        live = _load_live_trades(args.live_trades)
        live = live.rename(columns={"timestamp": "time"}).copy()
        live = live[(live["time"] >= start_dt) & (live["time"] <= end_dt)].copy()
        if live.empty:
            live, live_source = _load_live_events(args.live_fills, args.live_attempts)
            if not live.empty:
                live = live[(live["time"] >= start_dt) & (live["time"] <= end_dt)].copy()
    except Exception:
        live, live_source = _load_live_events(args.live_fills, args.live_attempts)
        if not live.empty:
            live = live[(live["time"] >= start_dt) & (live["time"] <= end_dt)].copy()

    backtest = _backtest_trades(snapshot, args.log_dir, end_dt)
    if not backtest.empty:
        backtest = backtest[(backtest["time"] >= start_dt) & (backtest["time"] <= end_dt)].copy()

    live_out = os.path.join(args.out_dir, "live_trades_since_snapshot.csv")
    backtest_out = os.path.join(args.out_dir, "hb_notional_010_trades_since_snapshot.csv")
    summary_out = os.path.join(args.out_dir, "trade_summary_since_snapshot.csv")
    chart_out = os.path.join(args.out_dir, "live_vs_backtest_trades_since_snapshot.html")
    attempts_out = os.path.join(args.out_dir, "live_attempts_since_snapshot.csv")
    attempts_chart_out = os.path.join(args.out_dir, "live_attempts_vs_backtest_trades_since_snapshot.html")

    live.to_csv(live_out, index=False)
    backtest.to_csv(backtest_out, index=False)

    summary_rows = [
        _summarize_trades(live, f"live ({live_source})"),
        _summarize_trades(backtest, "backtest"),
    ]
    with open(summary_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["label", "trades", "qty", "cost", "fees"])
        writer.writeheader()
        writer.writerows(summary_rows)

    _plot_cumulative_trades(backtest, live.rename(columns={"time": "timestamp"}), chart_out)

    attempts = _load_attempts(args.live_attempts)
    if not attempts.empty:
        attempts = attempts[(attempts["time"] >= start_dt) & (attempts["time"] <= end_dt)].copy()
        attempts.to_csv(attempts_out, index=False)
        _plot_cumulative_trades(backtest, attempts.rename(columns={"time": "timestamp"}), attempts_chart_out)

    print("Window:", start_dt, "to", end_dt)
    print("Live trades:", len(live), f"(source: {live_source})")
    print("Backtest trades:", len(backtest))
    print("Wrote:")
    print(" ", live_out)
    print(" ", backtest_out)
    print(" ", summary_out)
    print(" ", chart_out)
    if not attempts.empty:
        print(" ", attempts_out)
        print(" ", attempts_chart_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
