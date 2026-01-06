import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.replace("T", " ").replace("_", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # Snapshot timestamp format: YYYY-MM-DD_HHMMSS
    try:
        return datetime.strptime(value, "%Y-%m-%d_%H%M%S")
    except ValueError:
        return None


def _latest_snapshot(snap_dir: str) -> str | None:
    if not os.path.isdir(snap_dir):
        return None
    candidates: list[tuple[float, str]] = []
    for name in os.listdir(snap_dir):
        if not re.match(r"snapshot_\d{4}-\d{2}-\d{2}_\d{6}\.json", name):
            continue
        path = os.path.join(snap_dir, name)
        try:
            candidates.append((os.path.getmtime(path), path))
        except OSError:
            continue
    if not candidates:
        return None
    return max(candidates)[1]


def _latest_market_timestamp(market_dir: str, target_date: datetime) -> datetime | None:
    max_dt = None
    if not os.path.isdir(market_dir):
        return None
    for name in os.listdir(market_dir):
        if not (name.startswith("market_data_") and name.endswith(".csv")):
            continue
        path = os.path.join(market_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row.get("timestamp")
                    if not ts:
                        continue
                    try:
                        dt = datetime.fromisoformat(ts)
                    except Exception:
                        continue
                    if dt.date() != target_date.date():
                        continue
                    if max_dt is None or dt > max_dt:
                        max_dt = dt
        except OSError:
            continue
    return max_dt


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-16") as f:
            return json.load(f)
    except Exception:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def _parse_live_status_from_output(output_log: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    if not os.path.exists(output_log):
        return []

    anchor_date = None
    status = []
    current_date = None
    last_time = None
    current_time = None

    with open(output_log, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if anchor_date is None:
                m = re.search(r"snapshot_(\d{4}-\d{2}-\d{2})_\d{6}", line)
                if m:
                    anchor_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            m = re.search(r"--- Status @ (\d{2}:\d{2}:\d{2}) ---", line)
            if m:
                current_time = datetime.strptime(m.group(1), "%H:%M:%S").time()
                if current_date is None:
                    current_date = anchor_date or start_dt.date()
                elif last_time and current_time < last_time:
                    current_date = current_date.fromordinal(current_date.toordinal() + 1)
                last_time = current_time
                continue
            m = re.search(r"Equity: \$([\d\.]+)", line)
            if m and current_time and current_date:
                equity = float(m.group(1))
                dt = datetime.combine(current_date, current_time)
                if start_dt <= dt <= end_dt:
                    status.append({"time": dt.isoformat(), "equity": equity})
                current_time = None

    return status


def _parse_live_status_from_snapshots(status_dir: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    if not os.path.isdir(status_dir):
        return []
    status = []
    for name in os.listdir(status_dir):
        if not (name.startswith("trader_status_") and name.endswith(".json")):
            continue
        path = os.path.join(status_dir, name)
        try:
            snap = json.load(open(path, "r", encoding="utf-8"))
        except Exception:
            continue
        ts = snap.get("last_update")
        if not ts:
            continue
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if not (start_dt <= dt <= end_dt):
            continue
        equity = snap.get("equity")
        if equity is None:
            continue
        status.append({"time": dt.isoformat(), "equity": float(equity)})
    status.sort(key=lambda x: x["time"])
    return status


def _load_market_rows(market_dir: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    rows = []
    for name in os.listdir(market_dir):
        if not (name.startswith("market_data_") and name.endswith(".csv")):
            continue
        path = os.path.join(market_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                ts = r.get("timestamp")
                if not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(ts)
                except Exception:
                    continue
                if dt < start_dt or dt > end_dt:
                    continue
                r["_dt"] = dt
                rows.append(r)
    rows.sort(key=lambda r: r["_dt"])
    return rows


def _snapshot_start_equity(snapshot_path: str) -> float:
    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    cash = float(snap.get("balance") or snap.get("daily_start_equity") or 0.0)
    positions = snap.get("positions") or {}
    total_cost = 0.0
    for info in positions.values():
        try:
            total_cost += float(info.get("cost") or 0.0)
        except (TypeError, ValueError):
            continue
    return cash + total_cost


def _compute_local_equity(trades_path: str, snapshot_path: str, market_dir: str, start_dt: datetime, end_dt: datetime):
    trades = []
    with open(trades_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t = datetime.fromisoformat(r["time"])
            if t < start_dt or t > end_dt:
                continue
            trades.append(
                {
                    "time": t,
                    "action": r["action"],
                    "ticker": r["ticker"],
                    "price": float(r["price"]),
                    "qty": int(r["qty"]),
                    "fee": float(r.get("fee") or 0.0),
                }
            )
    trades.sort(key=lambda x: x["time"])

    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    cash = float(snap.get("balance") or snap.get("daily_start_equity") or 0.0)
    positions = snap.get("positions") or {}
    pos_yes = {k: int(v.get("yes") or 0) for k, v in positions.items()}
    pos_no = {k: int(v.get("no") or 0) for k, v in positions.items()}
    last_prices = {}
    # Seed mid prices from snapshot cost basis so starting equity reflects cash + position cost.
    for ticker, info in positions.items():
        yes_qty = int(info.get("yes") or 0)
        no_qty = int(info.get("no") or 0)
        cost = info.get("cost")
        if cost is None:
            continue
        try:
            cost = float(cost)
        except (TypeError, ValueError):
            continue
        if yes_qty > 0 and no_qty == 0:
            last_prices[ticker] = (cost / yes_qty) * 100.0
        elif no_qty > 0 and yes_qty == 0:
            last_prices[ticker] = 100.0 - ((cost / no_qty) * 100.0)
        elif yes_qty > 0 and no_qty > 0 and yes_qty != no_qty:
            mid = (cost * 100.0 - (no_qty * 100.0)) / (yes_qty - no_qty)
            if 0.0 <= mid <= 100.0:
                last_prices[ticker] = mid

    local = []
    local_trades = []
    trade_idx = 0

    def apply_trade(tr):
        nonlocal cash
        notional = (tr["price"] / 100.0) * tr["qty"]
        fee = tr["fee"]
        action = tr["action"]
        ticker = tr["ticker"]
        if action == "BUY_YES":
            cash -= (notional + fee)
            pos_yes[ticker] = pos_yes.get(ticker, 0) + tr["qty"]
        elif action == "BUY_NO":
            cash -= (notional + fee)
            pos_no[ticker] = pos_no.get(ticker, 0) + tr["qty"]
        elif action == "SELL_YES":
            cash += (notional - fee)
            pos_yes[ticker] = pos_yes.get(ticker, 0) - tr["qty"]
        elif action == "SELL_NO":
            cash += (notional - fee)
            pos_no[ticker] = pos_no.get(ticker, 0) - tr["qty"]

    def compute_equity():
        holdings = 0.0
        for t, q in pos_yes.items():
            mid = last_prices.get(t)
            if mid is None:
                continue
            holdings += q * (mid / 100.0)
        for t, q in pos_no.items():
            mid = last_prices.get(t)
            if mid is None:
                continue
            holdings += q * ((100.0 - mid) / 100.0)
        return cash + holdings

    rows = _load_market_rows(market_dir, start_dt, end_dt)
    for r in rows:
        t = r["_dt"]
        while trade_idx < len(trades) and trades[trade_idx]["time"] <= t:
            tr = trades[trade_idx]
            apply_trade(tr)
            local_trades.append({"time": tr["time"].isoformat(), "equity": compute_equity()})
            trade_idx += 1

        try:
            yes_bid = float(r.get("best_yes_bid")) if r.get("best_yes_bid") not in (None, "") else float("nan")
            no_ask = float(r.get("implied_no_ask")) if r.get("implied_no_ask") not in (None, "") else float("nan")
            yes_ask = float(r.get("implied_yes_ask")) if r.get("implied_yes_ask") not in (None, "") else float("nan")
        except Exception:
            yes_bid = float("nan")
            no_ask = float("nan")
            yes_ask = float("nan")

        yb = yes_bid
        if yb != yb and no_ask == no_ask:
            yb = 100.0 - no_ask
        ya = yes_ask
        if yb == yb and ya == ya:
            last_prices[r.get("market_ticker")] = (yb + ya) / 2.0
    local.append({"time": t.isoformat(), "equity": compute_equity()})

    while trade_idx < len(trades):
        tr = trades[trade_idx]
        apply_trade(tr)
        local_trades.append({"time": tr["time"].isoformat(), "equity": compute_equity()})
        trade_idx += 1

    return local, local_trades


def _compute_live_equity_from_fills(
    fills_path: str, snapshot_path: str, market_dir: str, start_dt: datetime, end_dt: datetime
):
    fills_blob = _load_json(fills_path)
    fills = []
    for fill in fills_blob.get("fills", []):
        ts = fill.get("ts")
        if ts is None:
            continue
        dt = datetime.fromtimestamp(ts)
        if dt < start_dt or dt > end_dt:
            continue
        side = (fill.get("side") or "").lower()
        action = (fill.get("action") or "").lower()
        price = fill.get("yes_price") if side == "yes" else fill.get("no_price")
        if price is None:
            continue
        fills.append(
            {
                "time": dt,
                "action": action,
                "ticker": fill.get("market_ticker") or fill.get("ticker"),
                "side": side,
                "price": float(price),
                "qty": int(fill.get("count") or 0),
            }
        )
    fills.sort(key=lambda x: x["time"])

    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    cash = float(snap.get("balance") or snap.get("daily_start_equity") or 0.0)
    positions = snap.get("positions") or {}
    pos_yes = {k: int(v.get("yes") or 0) for k, v in positions.items()}
    pos_no = {k: int(v.get("no") or 0) for k, v in positions.items()}
    last_prices = {}

    live = []
    live_trades = []
    fill_idx = 0

    def convex_fee(price_cents: float, qty: int) -> float:
        p = price_cents / 100.0
        raw = 0.07 * qty * p * (1 - p)
        fee = (int(raw * 100 + 0.9999999)) / 100.0
        return fee

    def apply_fill(tr):
        nonlocal cash
        notional = (tr["price"] / 100.0) * tr["qty"]
        fee = convex_fee(tr["price"], tr["qty"])
        ticker = tr["ticker"]
        if tr["action"] == "buy":
            cash -= (notional + fee)
            if tr["side"] == "yes":
                pos_yes[ticker] = pos_yes.get(ticker, 0) + tr["qty"]
            else:
                pos_no[ticker] = pos_no.get(ticker, 0) + tr["qty"]
        elif tr["action"] == "sell":
            cash += (notional - fee)
            if tr["side"] == "yes":
                pos_yes[ticker] = pos_yes.get(ticker, 0) - tr["qty"]
            else:
                pos_no[ticker] = pos_no.get(ticker, 0) - tr["qty"]

    def compute_equity():
        holdings = 0.0
        for t, q in pos_yes.items():
            mid = last_prices.get(t)
            if mid is None:
                continue
            holdings += q * (mid / 100.0)
        for t, q in pos_no.items():
            mid = last_prices.get(t)
            if mid is None:
                continue
            holdings += q * ((100.0 - mid) / 100.0)
        return cash + holdings

    rows = _load_market_rows(market_dir, start_dt, end_dt)
    for r in rows:
        t = r["_dt"]
        while fill_idx < len(fills) and fills[fill_idx]["time"] <= t:
            tr = fills[fill_idx]
            apply_fill(tr)
            live_trades.append({"time": tr["time"].isoformat(), "equity": compute_equity()})
            fill_idx += 1

        try:
            yes_bid = float(r.get("best_yes_bid")) if r.get("best_yes_bid") not in (None, "") else float("nan")
            no_ask = float(r.get("implied_no_ask")) if r.get("implied_no_ask") not in (None, "") else float("nan")
            yes_ask = float(r.get("implied_yes_ask")) if r.get("implied_yes_ask") not in (None, "") else float("nan")
        except Exception:
            yes_bid = float("nan")
            no_ask = float("nan")
            yes_ask = float("nan")

        yb = yes_bid
        if yb != yb and no_ask == no_ask:
            yb = 100.0 - no_ask
        ya = yes_ask
        if yb == yb and ya == ya:
            last_prices[r.get("market_ticker")] = (yb + ya) / 2.0
        live.append({"time": t.isoformat(), "equity": compute_equity()})

    while fill_idx < len(fills):
        tr = fills[fill_idx]
        apply_fill(tr)
        live_trades.append({"time": tr["time"].isoformat(), "equity": compute_equity()})
        fill_idx += 1

    return live, live_trades


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate live vs backtest comparison chart.")
    parser.add_argument("--snapshot-dir", default=os.path.join("vm_logs", "snapshots"))
    parser.add_argument("--snapshot", default="")
    parser.add_argument("--market-dir", default=os.path.join("vm_logs", "market_logs"))
    parser.add_argument("--output-log", default=os.path.join("server_mirror", "output.log"))
    parser.add_argument("--fills", default=os.path.join("vm_logs", "todays_fills.json"))
    parser.add_argument("--status-dir", default=os.path.join("vm_logs", "snapshots"))
    parser.add_argument("--strategy", default="backtesting.strategies.v3_variants:hb_notional_010")
    parser.add_argument("--min-requote-interval", type=float, default=0.0)
    parser.add_argument("--out-dir", default="unified_engine_out_snapshot_live")
    parser.add_argument("--graph", default=os.path.join("backtest_charts", "shadow_vs_local_roi_timeline.html"))
    parser.add_argument("--start-ts", default="")
    parser.add_argument("--end-ts", default="")
    parser.add_argument("--skip-backtest", action="store_true")
    args = parser.parse_args()

    snapshot_path = args.snapshot or _latest_snapshot(args.snapshot_dir)
    if not snapshot_path:
        raise SystemExit("No snapshot found. Provide --snapshot.")

    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    snap_ts = snap.get("timestamp") or snap.get("snapshot_time")
    start_dt = _parse_timestamp(args.start_ts or str(snap_ts))
    if not start_dt:
        raise SystemExit("Could not parse snapshot start timestamp.")

    end_dt = _parse_timestamp(args.end_ts) if args.end_ts else _latest_market_timestamp(args.market_dir, start_dt)
    if not end_dt:
        raise SystemExit("Could not determine end timestamp from market logs.")

    if not args.skip_backtest:
        cmd = [
            sys.executable,
            "-m",
            "unified_engine.runner",
            "--strategy",
            args.strategy,
            "--log-dir",
            args.market_dir,
            "--snapshot",
            snapshot_path,
            "--min-requote-interval",
            str(args.min_requote_interval),
            "--start-ts",
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "--end-ts",
            end_dt.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "--out-dir",
            args.out_dir,
        ]
        subprocess.run(cmd, check=True)

    trades_path = os.path.join(args.out_dir, "unified_trades.csv")
    if not os.path.exists(trades_path):
        raise SystemExit(f"Missing backtest trades: {trades_path}")

    local, local_trades = _compute_local_equity(
        trades_path, snapshot_path, args.market_dir, start_dt, end_dt
    )

    live = []
    live_trade_points = []
    if os.path.exists(args.fills):
        live, live_trade_points = _compute_live_equity_from_fills(
            args.fills, snapshot_path, args.market_dir, start_dt, end_dt
        )
    if not live:
        live = _parse_live_status_from_output(args.output_log, start_dt, end_dt)
    if not live:
        live = _parse_live_status_from_snapshots(args.status_dir, start_dt, end_dt)
    # Ensure live line starts at snapshot equity (cash + position cost).
    start_equity = _snapshot_start_equity(snapshot_path)
    if not live:
        live = [{"time": start_dt.isoformat(), "equity": start_equity}]
    else:
        first_time = datetime.fromisoformat(live[0]["time"])
        if first_time > start_dt:
            live.insert(0, {"time": start_dt.isoformat(), "equity": start_equity})

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Live vs Backtest (Unified)</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    #chart {{ height: 560px; }}
  </style>
</head>
<body>
  <h2>Live Unified vs Backtest ({start_dt.isoformat()} → {end_dt.isoformat()})</h2>
  <div id="chart"></div>
  <script>
    const live = {json.dumps(live)};
    const local = {json.dumps(local)};
    const liveTrades = {json.dumps(live_trade_points)};
    const localTrades = {json.dumps(local_trades)};

    const traces = [
      {{ x: live.map(p => p.time), y: live.map(p => p.equity), mode: 'lines', name: 'Live trader', line: {{ color: '#222222', width: 3 }} }},
      {{ x: local.map(p => p.time), y: local.map(p => p.equity), mode: 'lines', name: 'Backtest (replay)', line: {{ color: '#d46a3b' }} }},
      {{ x: liveTrades.map(p => p.time), y: liveTrades.map(p => p.equity), mode: 'markers', name: 'Live trades', marker: {{ size: 7, color: '#f5b700', symbol: 'circle' }} }},
      {{ x: localTrades.map(p => p.time), y: localTrades.map(p => p.equity), mode: 'markers', name: 'Backtest trades', marker: {{ size: 7, color: '#ff7a1a', symbol: 'circle' }} }}
    ];

    const layout = {{
      xaxis: {{ title: 'Time' }},
      yaxis: {{ title: 'Equity ($)' }},
      margin: {{ l: 60, r: 20, t: 20, b: 40 }},
      hovermode: 'closest'
    }};

    Plotly.newPlot('chart', traces, layout, {{ displayModeBar: false }});
  </script>
</body>
</html>"""

    os.makedirs(os.path.dirname(args.graph), exist_ok=True)
    with open(args.graph, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {args.graph} (live={len(live)} local={len(local)} trades live={len(live_trade_points)} local={len(local_trades)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
