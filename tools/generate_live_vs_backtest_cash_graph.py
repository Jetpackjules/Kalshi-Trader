import argparse
import csv
import json
import os
import re
from datetime import datetime, timedelta, time as dt_time


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.replace("T", " ").replace("_", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H%M%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _coerce_last_trade(value):
    if value in (None, ""):
        return None
    if isinstance(value, list):
        if not value:
            return None
        value = value[-1]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ticker_market_date(ticker: str) -> datetime | None:
    if not ticker:
        return None
    parts = ticker.split("-")
    if len(parts) < 2:
        return None
    raw = parts[1].upper()
    try:
        return datetime.strptime(raw, "%y%b%d")
    except ValueError:
        return None


def _latest_snapshot(snapshot_dir: str) -> str | None:
    if not os.path.isdir(snapshot_dir):
        return None
    latest = None
    latest_mtime = None
    for name in os.listdir(snapshot_dir):
        if not (name.startswith("snapshot_") and name.endswith(".json")):
            continue
        path = os.path.join(snapshot_dir, name)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if latest_mtime is None or mtime > latest_mtime:
            latest_mtime = mtime
            latest = path
    return latest


def _market_date_from_filename(name: str) -> datetime | None:
    match = re.match(r"market_data_(.+)\.csv$", name)
    if not match:
        return None
    return _ticker_market_date(match.group(1))


def _update_last_prices_from_row(row: dict, last_prices: dict) -> None:
    last_trade = row.get("last_trade_price")
    if last_trade in (None, ""):
        extras = row.get(None)
        if extras:
            last_trade = extras[-1] if isinstance(extras, list) else extras
    last_trade = _coerce_last_trade(last_trade)
    ticker = (row.get("market_ticker") or "").strip()
    if not ticker:
        return
    if last_trade is not None:
        last_prices[ticker] = float(last_trade)
        return
    try:
        yes_bid = float(row.get("best_yes_bid")) if row.get("best_yes_bid") not in (None, "") else float("nan")
        no_ask = (
            float(row.get("implied_no_ask")) if row.get("implied_no_ask") not in (None, "") else float("nan")
        )
        yes_ask = (
            float(row.get("implied_yes_ask")) if row.get("implied_yes_ask") not in (None, "") else float("nan")
        )
    except Exception:
        return
    yb = yes_bid
    if yb != yb and no_ask == no_ask:
        yb = 100.0 - no_ask
    ya = yes_ask
    if yb == yb and ya == ya:
        last_prices[ticker] = (yb + ya) / 2.0


def _seed_last_prices_before_start(
    market_dir: str, tickers: set[str], start_dt: datetime
) -> dict[str, float]:
    if not tickers:
        return {}
    last_prices: dict[str, float] = {}
    start_date = start_dt.date()
    for name in os.listdir(market_dir):
        if not (name.startswith("market_data_") and name.endswith(".csv")):
            continue
        market_date = _market_date_from_filename(name)
        if market_date and market_date.date() > start_date:
            continue
        path = os.path.join(market_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = _parse_timestamp(row.get("timestamp") or "")
                if not ts:
                    continue
                if ts > start_dt:
                    break
                ticker = (row.get("market_ticker") or "").strip()
                if ticker and ticker in tickers:
                    _update_last_prices_from_row(row, last_prices)
    return last_prices


def _load_market_rows(market_dir: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    rows = []
    start_date = start_dt.date()
    end_date = end_dt.date()
    for name in os.listdir(market_dir):
        if not (name.startswith("market_data_") and name.endswith(".csv")):
            continue
        market_date = _market_date_from_filename(name)
        if market_date:
            # Skip files clearly outside the requested window.
            if market_date.date() < start_date:
                continue
            if market_date.date() > end_date:
                continue
        path = os.path.join(market_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                ts = _parse_timestamp(r.get("timestamp") or "")
                if not ts:
                    continue
                if ts < start_dt:
                    continue
                if ts > end_dt:
                    break
                r["_dt"] = ts
                rows.append(r)
    rows.sort(key=lambda r: r["_dt"])
    return rows


def _resample_to_timestamps(source: list[dict], target: list[dict]) -> list[dict]:
    if not source or not target:
        return []
    src_times = [datetime.fromisoformat(p["time"]) for p in source]
    src_vals = [p["cash"] for p in source]
    resampled = []
    idx = 0
    for tp in target:
        t = datetime.fromisoformat(tp["time"])
        # Find nearest source time.
        while idx < len(src_times) and src_times[idx] < t:
            idx += 1
        if idx == 0:
            val = src_vals[0]
        elif idx >= len(src_times):
            val = src_vals[-1]
        else:
            before = src_times[idx - 1]
            after = src_times[idx]
            val = src_vals[idx - 1] if (t - before) <= (after - t) else src_vals[idx]
        resampled.append({"time": tp["time"], "cash": val})
    return resampled


def _parse_live_cash_from_output(output_log: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    if not os.path.exists(output_log):
        return []
    anchor_date = None
    status = []
    current_date = None
    last_time = None
    current_time = None
    with open(output_log, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.search(r"snapshot_(\d{4}-\d{2}-\d{2})_", line)
            if m:
                anchor_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            m = re.search(r"--- Status @ (\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?) ---", line)
            if m:
                time_str = m.group(1)
                fmt = "%H:%M:%S.%f" if "." in time_str else "%H:%M:%S"
                current_time = datetime.strptime(time_str, fmt).time()
                if current_date is None:
                    current_date = anchor_date or start_dt.date()
                elif last_time and current_time < last_time:
                    current_date = current_date.fromordinal(current_date.toordinal() + 1)
                last_time = current_time
                continue
            if current_date is None or current_time is None:
                continue
            m = re.search(r"Cash: \$(\d+(?:\.\d+)?)", line)
            if not m:
                continue
            dt = datetime.combine(current_date, current_time)
            if dt < start_dt or dt > end_dt:
                continue
            cash = float(m.group(1))
            status.append({"time": dt.isoformat(), "cash": cash})
    return status


def _compute_backtest_cash(
    trades_path: str, snapshot_path: str, market_dir: str, start_dt: datetime, end_dt: datetime
) -> list[dict]:
    trades = []
    with open(trades_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t = _parse_timestamp(r.get("time") or "")
            if not t or t < start_dt or t > end_dt:
                continue
            trades.append(
                {
                    "time": t,
                    "action": (r.get("action") or "").strip(),
                    "price": float(r["price"]),
                    "qty": int(r["qty"]),
                    "fee": float(r.get("fee") or 0.0),
                    "ticker": (r.get("ticker") or "").strip(),
                }
            )
    trades.sort(key=lambda x: x["time"])

    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    cash = float(snap.get("balance") or snap.get("daily_start_equity") or 0.0)
    positions = snap.get("positions") or {}
    pos_yes = {k: int(v.get("yes") or 0) for k, v in positions.items()}
    pos_no = {k: int(v.get("no") or 0) for k, v in positions.items()}
    tickers = set(list(positions.keys()) + [t["ticker"] for t in trades if t["ticker"]])
    last_prices = _seed_last_prices_before_start(market_dir, tickers, start_dt)

    settle_times = {}
    for ticker in tickers:
        market_dt = _ticker_market_date(ticker)
        if market_dt is None:
            continue
        settle_times[ticker] = datetime.combine(market_dt.date() + timedelta(days=1), dt_time(5, 0, 0))
    settled = set()

    rows = _load_market_rows(market_dir, start_dt, end_dt)
    cash_series = []
    trade_idx = 0
    for r in rows:
        t = r["_dt"]
        while trade_idx < len(trades) and trades[trade_idx]["time"] <= t:
            tr = trades[trade_idx]
            notional = (tr["price"] / 100.0) * tr["qty"]
            fee = tr["fee"]
            action = tr["action"]
            ticker = tr["ticker"]
            if action in {"BUY_YES", "BUY_NO"}:
                cash -= (notional + fee)
                if action == "BUY_YES":
                    pos_yes[ticker] = pos_yes.get(ticker, 0) + tr["qty"]
                else:
                    pos_no[ticker] = pos_no.get(ticker, 0) + tr["qty"]
            elif action in {"SELL_YES", "SELL_NO"}:
                cash += (notional - fee)
                if action == "SELL_YES":
                    pos_yes[ticker] = pos_yes.get(ticker, 0) - tr["qty"]
                else:
                    pos_no[ticker] = pos_no.get(ticker, 0) - tr["qty"]
            trade_idx += 1

        _update_last_prices_from_row(r, last_prices)

        for ticker, settle_dt in settle_times.items():
            if ticker in settled:
                continue
            if t < settle_dt:
                continue
            price = last_prices.get(ticker)
            if price is None:
                continue
            settle_price = 100.0 if price >= 50.0 else 0.0
            cash += pos_yes.get(ticker, 0) * (settle_price / 100.0)
            cash += pos_no.get(ticker, 0) * ((100.0 - settle_price) / 100.0)
            pos_yes[ticker] = 0
            pos_no[ticker] = 0
            last_prices.pop(ticker, None)
            settled.add(ticker)

        cash_series.append({"time": t.isoformat(), "cash": cash})
    return cash_series


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate live vs backtest cash-only chart.")
    parser.add_argument("--snapshot-dir", default=os.path.join("vm_logs", "snapshots"))
    parser.add_argument("--snapshot", default="")
    parser.add_argument("--market-dir", default=os.path.join("vm_logs", "market_logs"))
    parser.add_argument("--output-log", default=os.path.join("server_mirror", "output.log"))
    parser.add_argument("--out-dir", default="unified_engine_out_snapshot_live")
    parser.add_argument("--live-trades", default=os.path.join("vm_logs", "trades.csv"))
    parser.add_argument("--graph", default=os.path.join("backtest_charts", "shadow_vs_local_cash_timeline.html"))
    parser.add_argument("--start-ts", default="")
    parser.add_argument("--end-ts", default="")
    parser.add_argument("--extra-trades", default="", help="Optional path to a second trades CSV to plot as a comparison line")
    parser.add_argument("--extra-label", default="Recommended Strategy", help="Label for the extra trades line")
    args = parser.parse_args()

    # Load Snapshot to get default start time
    snapshot_path = args.snapshot or _latest_snapshot(args.snapshot_dir)
    if not snapshot_path:
        raise SystemExit("No snapshot found.")
    
    snap_data = json.load(open(snapshot_path, "r", encoding="utf-8"))
    snap_ts_str = snap_data.get("timestamp") or snap_data.get("last_update")
    snap_dt = _parse_timestamp(snap_ts_str) if snap_ts_str else None

    start_dt = _parse_timestamp(args.start_ts) if args.start_ts else snap_dt
    end_dt = _parse_timestamp(args.end_ts) if args.end_ts else None

    live_cash_all = _parse_live_cash_from_output(
        args.output_log, datetime.min, datetime.max
    )

    if not start_dt or not end_dt:
        # If start_dt still missing, fallback to live data or market logs
        if not start_dt:
            if live_cash_all:
                live_times = [datetime.fromisoformat(p["time"]) for p in live_cash_all]
                start_dt = min(live_times)
            else:
                rows = _load_market_rows(args.market_dir, datetime.min, datetime.max)
                if rows:
                    start_dt = rows[0]["_dt"]

        # If end_dt missing, find the latest between live data and market logs
        if not end_dt:
            candidates = []
            if live_cash_all:
                candidates.append(max(datetime.fromisoformat(p["time"]) for p in live_cash_all))
            
            # Check market logs for latest tick
            market_rows = _load_market_rows(args.market_dir, datetime.min, datetime.max)
            if market_rows:
                candidates.append(market_rows[-1]["_dt"])
            
            if candidates:
                end_dt = max(candidates)
            else:
                raise SystemExit("Could not determine end time (no live data or market logs).")

    if not start_dt:
        raise SystemExit("Could not determine start time.")

    print(f"Detected Time Range: {start_dt} -> {end_dt}")

    trades_path = os.path.join(args.out_dir, "unified_trades.csv")
    if not os.path.exists(trades_path):
        raise SystemExit(f"Missing backtest trades: {trades_path}")

    backtest_cash = _compute_backtest_cash(trades_path, snapshot_path, args.market_dir, start_dt, end_dt)
    
    extra_cash = []
    if args.extra_trades:
        if not os.path.exists(args.extra_trades):
            print(f"WARNING: Extra trades file not found: {args.extra_trades}")
        else:
            print(f"Computing cash for extra trades: {args.extra_trades}")
            extra_cash = _compute_backtest_cash(args.extra_trades, snapshot_path, args.market_dir, start_dt, end_dt)
    
    # STRICT CLIPPING: Ensure live cash starts exactly at or after start_dt
    live_cash = [p for p in live_cash_all if start_dt <= datetime.fromisoformat(p["time"]) <= end_dt]
    
    if not live_cash and live_cash_all:
        print(f"WARNING: No live cash points found within {start_dt} and {end_dt}")
        print(f"Live data range: {min(p['time'] for p in live_cash_all)} to {max(p['time'] for p in live_cash_all)}")

    # Resample live cash to tick timestamps.
    live_cash_aligned = _resample_to_timestamps(live_cash, backtest_cash) if backtest_cash else []

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Live vs Backtest Cash</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    #chart {{ height: 560px; }}
  </style>
</head>
<body>
  <h2>Live vs Backtest Cash ({start_dt.isoformat()} -> {end_dt.isoformat()})</h2>
  <div id="chart"></div>
  <script>
    const backtest = {json.dumps(backtest_cash)};
    const live = {json.dumps(live_cash_aligned)};
    const extra = {json.dumps(extra_cash)};

    const traces = [
      {{ x: backtest.map(p => p.time), y: backtest.map(p => p.cash), mode: 'lines', name: 'Baseline Backtest', line: {{ color: '#d46a3b' }} }},
      ...(live.length ? [{{ x: live.map(p => p.time), y: live.map(p => p.cash), mode: 'lines', name: 'Live Cash', line: {{ color: '#2f6bff', width: 2 }} }}] : []),
      ...(extra.length ? [{{ x: extra.map(p => p.time), y: extra.map(p => p.cash), mode: 'lines', name: '{args.extra_label}', line: {{ color: '#9333ea', width: 2 }} }}] : []),
    ];

    const layout = {{
      xaxis: {{ title: 'Time' }},
      yaxis: {{ title: 'Cash ($)' }},
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
    print(f"Wrote {args.graph} (backtest={len(backtest_cash)} live={len(live_cash_aligned)} extra={len(extra_cash)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
