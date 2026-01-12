import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, time as dt_time
import bisect


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.replace("T", " ").replace("_", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H%M%S", "%Y-%m-%d"):
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


def _latest_market_timestamp(market_dir: str) -> datetime | None:
    if not os.path.isdir(market_dir):
        return None
    
    # Get all market data files and sort them by date (from filename)
    files = []
    for name in os.listdir(market_dir):
        if name.startswith("market_data_") and name.endswith(".csv"):
            files.append(name)
    
    if not files:
        return None
        
    # Sort files by the date in the filename (e.g., 26JAN10)
    # This is a bit tricky but since they are all 26JANxx, alphabetical sort works for now
    # or we can just sort by mtime as a proxy.
    files.sort() 
    
    # Check the last file first
    for name in reversed(files):
        path = os.path.join(market_dir, name)
        try:
            # Efficiently read the last line
            with open(path, "rb") as f:
                try:
                    f.seek(-2048, os.SEEK_END)
                except OSError:
                    pass # File smaller than 2kb
                last_lines = f.read().decode("utf-8", errors="ignore").splitlines()
                if not last_lines:
                    continue
                # Try the last few lines in case the very last one is incomplete
                for line in reversed(last_lines):
                    m = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", line)
                    if m:
                        return datetime.fromisoformat(m.group(1).replace(" ", "T"))
        except Exception:
            continue
    return None


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
            m = re.search(r"Equity: \$([\d\.]+)", line)
            if m and current_time and current_date:
                equity = float(m.group(1))
                dt = datetime.combine(current_date, current_time)
                if start_dt <= dt <= end_dt:
                    status.append({"time": dt.isoformat(), "equity": equity})
                current_time = None

    return status


def _load_decision_intents(path: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    points = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            decision_type = (row.get("decision_type") or "").strip().lower()
            action = (row.get("action") or "").strip().upper()
            if decision_type != "desired" or not action:
                continue
            tick_ts = _parse_timestamp(row.get("tick_time") or row.get("decision_time") or "")
            if not tick_ts:
                continue
            if tick_ts < start_dt or tick_ts > end_dt:
                continue
            points.append({"time": tick_ts.isoformat(), "action": action})
    return points


def _load_decision_rows(path: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tick_ts = _parse_timestamp(row.get("tick_time") or row.get("decision_time") or "")
            if not tick_ts:
                continue
            if tick_ts < start_dt or tick_ts > end_dt:
                continue
            decision_type = (row.get("decision_type") or "").strip().lower()
            action = (row.get("action") or "").strip().upper()
            price = row.get("price")
            qty = row.get("qty")
            rows.append(
                {
                    "tick_time": tick_ts,
                    "ticker": (row.get("ticker") or "").strip(),
                    "decision_type": decision_type,
                    "action": action,
                    "price": price if price not in (None, "") else None,
                    "qty": qty if qty not in (None, "") else None,
                }
            )
    rows.sort(key=lambda r: (r["tick_time"], r["ticker"]))
    return rows


def _find_first_decision_divergence(
    live_path: str, back_path: str, start_dt: datetime, end_dt: datetime
) -> dict | None:
    live_rows = _load_decision_rows(live_path, start_dt, end_dt)
    back_rows = _load_decision_rows(back_path, start_dt, end_dt)
    if not live_rows or not back_rows:
        return None

    live_min = live_rows[0]["tick_time"]
    live_max = live_rows[-1]["tick_time"]
    back_min = back_rows[0]["tick_time"]
    back_max = back_rows[-1]["tick_time"]

    overlap_start = max(live_min, back_min, start_dt)
    overlap_end = min(live_max, back_max, end_dt)
    if overlap_start > overlap_end:
        return None

    live_rows = [r for r in live_rows if overlap_start <= r["tick_time"] <= overlap_end]
    back_rows = [r for r in back_rows if overlap_start <= r["tick_time"] <= overlap_end]
    if not live_rows or not back_rows:
        return None

    live_index = {(r["tick_time"], r["ticker"]): r for r in live_rows}
    for b in back_rows:
        key = (b["tick_time"], b["ticker"])
        l = live_index.get(key)
        if not l:
            return {
                "time": b["tick_time"].isoformat(),
                "label": f"Decision divergence: {b['ticker']} missing live",
                "color": "#7a3fb3",
            }
        if (
            b["decision_type"] != l["decision_type"]
            or b["action"] != l["action"]
            or b["price"] != l["price"]
            or b["qty"] != l["qty"]
        ):
            label = (
                f"Decision divergence: {b['ticker']} "
                f"back={b['decision_type']} live={l['decision_type']}"
            )
            return {
                "time": b["tick_time"].isoformat(),
                "label": label,
                "color": "#7a3fb3",
            }
    return None


def _align_points_to_series(points: list[dict], series: list[dict]) -> list[dict]:
    if not points or not series:
        return []
    targets = [{"time": p["time"], "equity": 0.0} for p in points]
    resampled = _resample_to_timestamps(series, targets)
    return [
        {"time": p["time"], "equity": r["equity"], "action": p["action"]}
        for p, r in zip(points, resampled)
    ]


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
                last_trade = r.get("last_trade_price")
                # Handle unlabeled trailing last_trade_price column.
                if last_trade in (None, ""):
                    extras = r.get(None)
                    if extras:
                        last_trade = extras[-1] if isinstance(extras, list) else extras
                r["_last_trade"] = _coerce_last_trade(last_trade)
                rows.append(r)
    rows.sort(key=lambda r: r["_dt"])
    return rows


def _resample_to_timestamps(source: list[dict], target: list[dict]) -> list[dict]:
    if not source or not target:
        return []
    src_times = [datetime.fromisoformat(p["time"]) for p in source]
    src_vals = [p["equity"] for p in source]
    resampled = []
    for tp in target:
        t = datetime.fromisoformat(tp["time"])
        idx = bisect.bisect_left(src_times, t)
        if idx == 0:
            val = src_vals[0]
        elif idx >= len(src_times):
            val = src_vals[-1]
        else:
            before = src_times[idx - 1]
            after = src_times[idx]
            val = src_vals[idx - 1] if (t - before) <= (after - t) else src_vals[idx]
        resampled.append({"time": tp["time"], "equity": val})
    return resampled


def _last_mid_prices_at_timestamp(snapshot_path: str, market_dir: str, cutoff_dt: datetime) -> dict[str, float]:
    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    positions = snap.get("positions") or {}
    if not positions:
        return {}
    last_mid: dict[str, float] = {}
    for path in [p for p in os.listdir(market_dir) if p.startswith("market_data_") and p.endswith(".csv")]:
        full = os.path.join(market_dir, path)
        with open(full, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                ts = r.get("timestamp")
                if not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(ts)
                except Exception:
                    continue
                if dt > cutoff_dt:
                    continue
                ticker = r.get("market_ticker")
                if ticker not in positions:
                    continue
                last_trade = r.get("last_trade_price")
                if last_trade in (None, ""):
                    extras = r.get(None)
                    if extras:
                        last_trade = extras[-1] if isinstance(extras, list) else extras
                last_trade = _coerce_last_trade(last_trade)
                if last_trade is not None:
                    last_mid[ticker] = last_trade
                    continue
                try:
                    yb = float(r.get("best_yes_bid")) if r.get("best_yes_bid") not in (None, "") else None
                    na = float(r.get("implied_no_ask")) if r.get("implied_no_ask") not in (None, "") else None
                    ya = float(r.get("implied_yes_ask")) if r.get("implied_yes_ask") not in (None, "") else None
                except Exception:
                    yb = na = ya = None
                if yb is None and na is not None:
                    yb = 100.0 - na
                if yb is None or ya is None:
                    continue
                last_mid[ticker] = (yb + ya) / 2.0
    return last_mid


def _mtm_positions_at_timestamp(snapshot_path: str, market_dir: str, cutoff_dt: datetime) -> float:
    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    positions = snap.get("positions") or {}
    if not positions:
        return 0.0
    last_mid = _last_mid_prices_at_timestamp(snapshot_path, market_dir, cutoff_dt)
    holdings = 0.0
    for ticker, pos in positions.items():
        mid = last_mid.get(ticker)
        if mid is None:
            continue
        yes_qty = int(pos.get("yes") or 0)
        no_qty = int(pos.get("no") or 0)
        holdings += yes_qty * (mid / 100.0)
        holdings += no_qty * ((100.0 - mid) / 100.0)
    return holdings


def _snapshot_start_equity(snapshot_path: str) -> float:
    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    # Disregard daily_start_equity; use cash only for baseline.
    try:
        return float(snap.get("balance") or 0.0)
    except (TypeError, ValueError):
        return 0.0


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
    last_prices = _last_mid_prices_at_timestamp(snapshot_path, market_dir, start_dt)
    last_ask_prices = dict(last_prices)
    settle_times = {}
    for ticker in set(list(positions.keys()) + [t["ticker"] for t in trades]):
        market_dt = _ticker_market_date(ticker)
        if market_dt is None:
            continue
        settle_times[ticker] = datetime.combine(market_dt.date() + timedelta(days=1), dt_time(5, 0, 0))
    settled = set()

    # Seed missing mid prices from snapshot cost basis
    for ticker, info in positions.items():
        if ticker in last_prices:
            continue
        yes_qty = int(info.get("yes") or 0)
        no_qty = int(info.get("no") or 0)
        cost = info.get("cost")
        if cost is None: continue
        try: cost = float(cost)
        except: continue
        
        if yes_qty > 0 and no_qty == 0:
            last_prices[ticker] = (cost / yes_qty) * 100.0
        elif no_qty > 0 and yes_qty == 0:
            last_prices[ticker] = 100.0 - ((cost / no_qty) * 100.0)
        elif yes_qty > 0 and no_qty > 0 and yes_qty != no_qty:
            mid = (cost * 100.0 - (no_qty * 100.0)) / (yes_qty - no_qty)
            if 0.0 <= mid <= 100.0:
                last_prices[ticker] = mid

    print(f"DEBUG: Initial Cash: {cash}")
    print(f"DEBUG: Initial Positions: YES={pos_yes}, NO={pos_no}")
    print(f"DEBUG: Initial Last Prices: {last_prices}")

    local = []
    local_ask = []
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

    def compute_equity_ask():
        holdings = 0.0
        for t, q in pos_yes.items():
            ask = last_ask_prices.get(t)
            if ask is None:
                continue
            holdings += q * (ask / 100.0)
        for t, q in pos_no.items():
            ask = last_ask_prices.get(t)
            if ask is None:
                continue
            holdings += q * ((100.0 - ask) / 100.0)
        return cash + holdings

    rows = _load_market_rows(market_dir, start_dt, end_dt)
    print(f"DEBUG: Loaded {len(rows)} market rows and {len(trades)} backtest trades.")
    
    first_row = True
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

        if yes_ask == yes_ask:
            last_ask_prices[r.get("market_ticker")] = yes_ask

        last_trade = r.get("_last_trade")
        source = "quote"
        if last_trade is not None:
            try:
                last_prices[r.get("market_ticker")] = float(last_trade)
                source = "last_trade"
            except Exception:
                pass
        else:
            yb = yes_bid
            if yb != yb and no_ask == no_ask:
                yb = 100.0 - no_ask
            ya = yes_ask
            if yb == yb and ya == ya:
                last_prices[r.get("market_ticker")] = (yb + ya) / 2.0

        # Apply settlements once the market day has passed (5am next day).
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
            last_ask_prices.pop(ticker, None)
            settled.add(ticker)

        local_ask.append({"time": t.isoformat(), "equity": compute_equity_ask(), "source": "implied_yes_ask"})

        eq = compute_equity()
        local.append({"time": t.isoformat(), "equity": eq, "source": source})

    while trade_idx < len(trades):
        tr = trades[trade_idx]
        apply_trade(tr)
        local_trades.append({"time": tr["time"].isoformat(), "equity": compute_equity()})
        trade_idx += 1

    return local, local_trades, local_ask


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
    last_prices = _last_mid_prices_at_timestamp(snapshot_path, market_dir, start_dt)

    live = []
    live_trades = []
    live_portfolio = []
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

    def compute_holdings():
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
        return holdings

    def compute_equity():
        return cash + compute_holdings()

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

        last_trade = r.get("_last_trade")
        if last_trade is not None:
            try:
                last_prices[r.get("market_ticker")] = float(last_trade)
                live.append({"time": t.isoformat(), "equity": compute_equity(), "source": "last_trade"})
                live_portfolio.append({"time": t.isoformat(), "value": compute_holdings()})
                continue
            except Exception:
                pass

        yb = yes_bid
        if yb != yb and no_ask == no_ask:
            yb = 100.0 - no_ask
        ya = yes_ask
        if yb == yb and ya == ya:
            last_prices[r.get("market_ticker")] = (yb + ya) / 2.0
        live.append({"time": t.isoformat(), "equity": compute_equity(), "source": "quote"})
        live_portfolio.append({"time": t.isoformat(), "value": compute_holdings()})

    while fill_idx < len(fills):
        tr = fills[fill_idx]
        apply_fill(tr)
        live_trades.append({"time": tr["time"].isoformat(), "equity": compute_equity()})
        fill_idx += 1

    return live, live_trades, live_portfolio


def _compute_live_equity_from_csv(
    csv_path: str,
    snapshot_path: str,
    market_dir: str,
    start_dt: datetime,
    end_dt: datetime,
    prefer_mtm_seed: bool = True,
):
    trades = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Format: time,action,ticker,price,qty,fee,cost,source,order_id
            # OR legacy: timestamp,strategy,ticker,action,price,qty,cost,fee,position_id,market_id
            
            ts_str = row.get("time") or row.get("timestamp")
            if not ts_str:
                continue
                
            try:
                # Try standard ISO format first
                dt = datetime.fromisoformat(ts_str)
            except ValueError:
                try:
                    # Try space-separated format often used in logs
                    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    continue

            if dt < start_dt or dt > end_dt:
                # print(f"Dropping trade at {dt} (outside range)")
                continue

            action = row.get("action", "").upper()
            ticker = row.get("ticker", "")
            try:
                price = float(row.get("price", 0))
                qty = int(row.get("qty", 0))
                fee = float(row.get("fee", 0))
            except ValueError:
                continue

            trades.append({
                "time": dt,
                "action": action,
                "ticker": ticker,
                "price": price,
                "qty": qty,
                "fee": fee
            })

    trades.sort(key=lambda x: x["time"])

    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    cash = float(snap.get("balance") or snap.get("daily_start_equity") or 0.0)
    positions = snap.get("positions") or {}
    pos_yes = {k: int(v.get("yes") or 0) for k, v in positions.items()}
    pos_no = {k: int(v.get("no") or 0) for k, v in positions.items()}
    last_prices = _last_mid_prices_at_timestamp(snapshot_path, market_dir, start_dt) if prefer_mtm_seed else {}
    # Seed missing mid prices from snapshot cost basis
    for ticker, info in positions.items():
        if prefer_mtm_seed and ticker in last_prices:
            continue
        yes_qty = int(info.get("yes") or 0)
        no_qty = int(info.get("no") or 0)
        cost = info.get("cost")
        if cost is None: continue
        try: cost = float(cost)
        except: continue
        
        if yes_qty > 0 and no_qty == 0:
            last_prices[ticker] = (cost / yes_qty) * 100.0
        elif no_qty > 0 and yes_qty == 0:
            last_prices[ticker] = 100.0 - ((cost / no_qty) * 100.0)
        elif yes_qty > 0 and no_qty > 0 and yes_qty != no_qty:
            mid = (cost * 100.0 - (no_qty * 100.0)) / (yes_qty - no_qty)
            if 0.0 <= mid <= 100.0:
                last_prices[ticker] = mid

    live = []
    live_trades = []
    live_portfolio = []
    trade_idx = 0

    def apply_trade(tr):
        nonlocal cash
        notional = (tr["price"] / 100.0) * tr["qty"]
        fee = tr["fee"]
        ticker = tr["ticker"]
        action = tr["action"] # BUY_YES, SELL_NO, etc.
        
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

    def compute_holdings():
        holdings = 0.0
        for t, q in pos_yes.items():
            mid = last_prices.get(t)
            if mid is None: continue
            holdings += q * (mid / 100.0)
        for t, q in pos_no.items():
            mid = last_prices.get(t)
            if mid is None: continue
            holdings += q * ((100.0 - mid) / 100.0)
        return holdings

    def compute_equity():
        return cash + compute_holdings()

    rows = _load_market_rows(market_dir, start_dt, end_dt)
    for r in rows:
        t = r["_dt"]
        while trade_idx < len(trades) and trades[trade_idx]["time"] <= t:
            tr = trades[trade_idx]
            apply_trade(tr)
            live_trades.append({"time": tr["time"].isoformat(), "equity": compute_equity()})
            trade_idx += 1

        try:
            yes_bid = float(r.get("best_yes_bid")) if r.get("best_yes_bid") not in (None, "") else float("nan")
            no_ask = float(r.get("implied_no_ask")) if r.get("implied_no_ask") not in (None, "") else float("nan")
            yes_ask = float(r.get("implied_yes_ask")) if r.get("implied_yes_ask") not in (None, "") else float("nan")
        except Exception:
            yes_bid = float("nan")
            no_ask = float("nan")
            yes_ask = float("nan")

        last_trade = r.get("_last_trade")
        if last_trade is not None:
            try:
                last_prices[r.get("market_ticker")] = float(last_trade)
                live.append({"time": t.isoformat(), "equity": compute_equity(), "source": "last_trade"})
                live_portfolio.append({"time": t.isoformat(), "value": compute_holdings()})
                continue
            except Exception:
                pass

        yb = yes_bid
        if yb != yb and no_ask == no_ask:
            yb = 100.0 - no_ask
        ya = yes_ask
        if yb == yb and ya == ya:
            last_prices[r.get("market_ticker")] = (yb + ya) / 2.0
        live.append({"time": t.isoformat(), "equity": compute_equity(), "source": "quote"})
        live_portfolio.append({"time": t.isoformat(), "value": compute_holdings()})

    while trade_idx < len(trades):
        tr = trades[trade_idx]
        apply_trade(tr)
        live_trades.append({"time": tr["time"].isoformat(), "equity": compute_equity()})
        trade_idx += 1

    return live, live_trades, live_portfolio


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate live vs backtest comparison chart.")
    parser.add_argument("--snapshot-dir", default=os.path.join("vm_logs", "snapshots"))
    parser.add_argument("--snapshot", default="")
    parser.add_argument("--market-dir", default=os.path.join("vm_logs", "market_logs"))
    parser.add_argument("--output-log", default=os.path.join("server_mirror", "output.log"))
    parser.add_argument("--fills", default=os.path.join("vm_logs", "todays_fills.json"))
    parser.add_argument("--live-trades", default=os.path.join("vm_logs", "trades.csv"))
    parser.add_argument("--live-decisions", default=os.path.join("vm_logs", "unified_engine_out", "decision_intents.csv"))
    parser.add_argument("--backtest-decisions", default="")
    parser.add_argument("--unified-csv", type=str, help="Path to unified engine equity_history.csv")
    parser.add_argument("--status-dir", default=os.path.join("vm_logs", "snapshots"))
    parser.add_argument("--strategy", default="backtesting.strategies.v3_variants:hb_notional_010")
    parser.add_argument("--min-requote-interval", type=float, default=2.0)
    parser.add_argument("--out-dir", default="unified_engine_out_snapshot_live")
    parser.add_argument("--graph", default=os.path.join("backtest_charts", "shadow_vs_local_roi_timeline.html"))
    parser.add_argument("--start-ts", default="")
    parser.add_argument("--end-ts", default="")
    parser.add_argument("--skip-backtest", action="store_true")
    parser.add_argument("--backtest-start-equity", type=float, default=None)
    parser.add_argument("--backtest-start-equity-from-reported", action="store_true")
    parser.add_argument(
        "--live-seed-cost-basis",
        action="store_true",
        help="Seed live CSV equity from snapshot cost basis (override MTM seed).",
    )
    parser.add_argument(
        "--replay-live-trades",
        action="store_true",
        help="Replay live trades against market logs instead of running the backtest.",
    )
    args = parser.parse_args()

    snapshot_path = args.snapshot or _latest_snapshot(args.snapshot_dir)
    if not snapshot_path:
        raise SystemExit("No snapshot found. Provide --snapshot.")

    snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
    snap_ts = snap.get("last_update") or snap.get("timestamp") or snap.get("snapshot_time")
    start_dt = _parse_timestamp(args.start_ts or str(snap_ts))
    if not start_dt:
        raise SystemExit("Could not parse snapshot start timestamp.")

    end_dt = _parse_timestamp(args.end_ts) if args.end_ts else _latest_market_timestamp(args.market_dir)
    if not end_dt:
        raise SystemExit("Could not determine end timestamp from market logs.")

    print(f"Time Range: {start_dt} -> {end_dt}")

    # Load Unified Backtest Data if provided
    unified_series = []
    if args.unified_csv and os.path.exists(args.unified_csv):
        print(f"Loading Unified Backtest data from {args.unified_csv}...")
        with open(args.unified_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dt = _parse_timestamp(row.get("date"))
                if not dt: continue
                if start_dt and dt < start_dt: continue
                if end_dt and dt > end_dt: continue
                unified_series.append({"time": dt.isoformat(), "equity": float(row["equity"])})
        unified_series.sort(key=lambda x: x["time"])
        print(f"Loaded {len(unified_series)} points from Unified Backtest.")

    # Optional: adjust backtest snapshot start equity to match reported baseline.
    backtest_snapshot_path = snapshot_path
    reported_baseline = None
    if args.backtest_start_equity_from_reported:
        reported_points = _parse_live_status_from_output(args.output_log, start_dt, end_dt)
        if reported_points:
            reported_baseline = reported_points[0]["equity"]
    if args.backtest_start_equity is not None:
        reported_baseline = args.backtest_start_equity

    if reported_baseline is not None:
        snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
        mtm_positions = _mtm_positions_at_timestamp(snapshot_path, args.market_dir, start_dt)
        try:
            snap["daily_start_equity"] = float(reported_baseline)
        except (TypeError, ValueError):
            pass
        try:
            snap["balance"] = float(reported_baseline) - float(mtm_positions)
        except (TypeError, ValueError):
            pass
        os.makedirs(args.out_dir, exist_ok=True)
        backtest_snapshot_path = os.path.join(args.out_dir, "snapshot_adjusted.json")
        with open(backtest_snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2)
        print(
            f"Using adjusted snapshot for backtest: {backtest_snapshot_path} "
            f"(start_equity={reported_baseline:.2f} mtm_positions={mtm_positions:.2f})"
        )

    if args.replay_live_trades and not os.path.exists(args.live_trades):
        raise SystemExit(f"Missing live trades for replay: {args.live_trades}")

    if not args.skip_backtest and not args.replay_live_trades:
        decision_log_path = os.path.join(args.out_dir, "decision_intents.csv")
        if os.path.exists(decision_log_path):
            os.remove(decision_log_path)
        cmd = [
            sys.executable,
            "-m",
            "unified_engine.runner",
            "--strategy",
            args.strategy,
            "--log-dir",
            args.market_dir,
            "--snapshot",
            backtest_snapshot_path,
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

    trades_path = args.live_trades if args.replay_live_trades else os.path.join(args.out_dir, "unified_trades.csv")
    if not os.path.exists(trades_path):
        raise SystemExit(f"Missing backtest trades: {trades_path}")

    local, local_trades, local_ask = _compute_local_equity(
        trades_path, backtest_snapshot_path, args.market_dir, start_dt, end_dt
    )

    live = []
    live_trade_points = []
    live_portfolio = []
    
    # Priority 1: trades.csv (New Standard)
    if os.path.exists(args.live_trades):
        print(f"Using live trades from: {args.live_trades}")
        live, live_trade_points, live_portfolio = _compute_live_equity_from_csv(
            args.live_trades,
            snapshot_path,
            args.market_dir,
            start_dt,
            end_dt,
            prefer_mtm_seed=not args.live_seed_cost_basis,
        )

    # Priority 2: todays_fills.json (Legacy)
    if not live and os.path.exists(args.fills):
        print(f"Using live fills from: {args.fills}")
        live, live_trade_points, live_portfolio = _compute_live_equity_from_fills(
            args.fills, snapshot_path, args.market_dir, start_dt, end_dt
        )
    if not live:
        live = _parse_live_status_from_output(args.output_log, start_dt, end_dt)
    if not live:
        live = _parse_live_status_from_snapshots(args.status_dir, start_dt, end_dt)
    # Ensure live line has at least one point (cash-only baseline if no ticks).
    if not live:
        live = [{"time": start_dt.isoformat(), "equity": _snapshot_start_equity(snapshot_path)}]

    baseline_equity = _snapshot_start_equity(snapshot_path) + _mtm_positions_at_timestamp(
        snapshot_path, args.market_dir, start_dt
    )

    # Additional line: reported equity from output.log, if available.
    reported = _parse_live_status_from_output(args.output_log, start_dt, end_dt)
    if reported:
        first_rep = datetime.fromisoformat(reported[0]["time"])
        if first_rep > start_dt:
            reported.insert(0, {"time": start_dt.isoformat(), "equity": baseline_equity})
    if local:
        first_local = datetime.fromisoformat(local[0]["time"])
        if first_local > start_dt:
            local.insert(0, {"time": start_dt.isoformat(), "equity": baseline_equity, "source": "baseline"})
    reported_on_ticks = []
    if reported and local:
        reported_on_ticks = _resample_to_timestamps(reported, local)
    elif reported:
        reported_on_ticks = list(reported)
    live_resampled = _resample_to_timestamps(live, reported) if reported else []
    # Offset backtest series to match reported baseline.
    local_aligned = []
    local_ask_aligned = []
    local_trades_aligned = []
    live_trade_points_aligned = []
    if local and reported:
        offset = reported[0]["equity"] - local[0]["equity"]
        local_aligned = [
            {"time": p["time"], "equity": p["equity"] + offset, "source": p.get("source")}
            for p in local
        ]
        if local_ask:
            local_ask_aligned = [
                {"time": p["time"], "equity": p["equity"] + offset, "source": p.get("source")}
                for p in local_ask
            ]
        if local_trades:
            local_trades_aligned = [
                {"time": p["time"], "equity": p["equity"] + offset} for p in local_trades
            ]
    elif local:
        local_aligned = list(local)
        if local_ask:
            local_ask_aligned = list(local_ask)
        if local_trades:
            local_trades_aligned = list(local_trades)
    live_aligned = list(live)
    if reported and live_trade_points:
        trade_targets = [{"time": p["time"], "equity": 0.0} for p in live_trade_points]
        resampled = _resample_to_timestamps(reported, trade_targets)
        live_trade_points_aligned = [
            {"time": p["time"], "equity": r["equity"]} for p, r in zip(live_trade_points, resampled)
        ]
    elif live_trade_points:
        live_trade_points_aligned = list(live_trade_points)

    backtest_decision_path = args.backtest_decisions or os.path.join(args.out_dir, "decision_intents.csv")
    live_decisions = _load_decision_intents(args.live_decisions, start_dt, end_dt)
    backtest_decisions = _load_decision_intents(backtest_decision_path, start_dt, end_dt)
    divergence_marker = _find_first_decision_divergence(
        args.live_decisions, backtest_decision_path, start_dt, end_dt
    )

    live_decisions_aligned = _align_points_to_series(
        live_decisions, reported if reported else live
    )
    backtest_decisions_aligned = _align_points_to_series(
        backtest_decisions, local_aligned if local_aligned else local
    )

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
      const reported = {json.dumps(reported_on_ticks)};
    const local = {json.dumps(local_aligned)};
    const unified = {json.dumps(unified_series)};
    const localAsk = {json.dumps(local_ask_aligned)};
    const liveTrades = {json.dumps(live_trade_points_aligned)};
    const localTrades = {json.dumps(local_trades_aligned)};
      const liveDecisions = {json.dumps(live_decisions_aligned)};
      const backtestDecisions = {json.dumps(backtest_decisions_aligned)};
      const markers = {json.dumps([divergence_marker] if divergence_marker else [])};

    const localTickColors = local.map(p => (
      p.source === 'last_trade' ? '#1f9e8a' :
      p.source === 'quote' ? '#d46a3b' :
      '#888888'
    ));

      const markerShapes = markers.map(m => ({{
        type: 'line',
        x0: m.time,
        x1: m.time,
        y0: 0,
        y1: 1,
        xref: 'x',
        yref: 'paper',
        line: {{ color: m.color, width: 1, dash: 'dot' }}
      }}));

      const markerAnnotations = markers.map(m => ({{
        x: m.time,
        y: 1,
        xref: 'x',
        yref: 'paper',
        text: m.label,
        showarrow: false,
        xanchor: 'left',
        yanchor: 'bottom',
        font: {{ size: 11, color: m.color }},
        bgcolor: 'rgba(255,255,255,0.7)',
        bordercolor: m.color,
        borderwidth: 1
      }}));

      const traces = [
        ...(reported.length ? [{{ x: reported.map(p => p.time), y: reported.map(p => p.equity), mode: 'lines', name: 'Live (reported, tick-time)', line: {{ color: '#2f6bff', width: 2 }} }}] : []),
      {{ x: local.map(p => p.time), y: local.map(p => p.equity), mode: 'lines', name: 'Backtest (replay)', line: {{ color: '#d46a3b' }} }},
      ...(unified.length ? [{{ x: unified.map(p => p.time), y: unified.map(p => p.equity), mode: 'lines', name: 'Unified Backtest', line: {{ color: '#9900cc', width: 3 }} }}] : []),
      ...(localAsk.length ? [{{ x: localAsk.map(p => p.time), y: localAsk.map(p => p.equity), mode: 'lines', name: 'Backtest (implied yes ask)', line: {{ color: '#2aa876', dash: 'dot' }} }}] : []),
      {{ x: liveTrades.map(p => p.time), y: liveTrades.map(p => p.equity), mode: 'markers', name: 'Live trades', marker: {{ size: 7, color: '#f5b700', symbol: 'circle' }} }},
      {{ x: localTrades.map(p => p.time), y: localTrades.map(p => p.equity), mode: 'markers', name: 'Backtest trades', marker: {{ size: 7, color: '#ff7a1a', symbol: 'circle' }} }},
      {{ x: liveDecisions.map(p => p.time), y: liveDecisions.map(p => p.equity), mode: 'markers', name: 'Live decisions', marker: {{ size: 6, color: '#1f9e8a', symbol: 'diamond' }} }},
      {{ x: backtestDecisions.map(p => p.time), y: backtestDecisions.map(p => p.equity), mode: 'markers', name: 'Backtest decisions', marker: {{ size: 6, color: '#7a3fb3', symbol: 'diamond' }} }}
    ];

      const layout = {{
        xaxis: {{ title: 'Time' }},
        yaxis: {{ title: 'Equity ($)' }},
        margin: {{ l: 60, r: 20, t: 20, b: 40 }},
        hovermode: 'closest',
        shapes: markerShapes,
        annotations: markerAnnotations
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
