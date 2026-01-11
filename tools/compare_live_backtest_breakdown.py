import argparse
import json
import os
import re
from datetime import datetime


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _latest_status_time(output_log: str) -> datetime | None:
    if not os.path.exists(output_log):
        return None
    anchor_date = None
    status_time = None
    with open(output_log, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    for line in lines:
        m = re.search(r"snapshot_(\d{4}-\d{2}-\d{2})_", line)
        if m:
            anchor_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("--- Status @"):
            time_str = lines[i].strip().split("--- Status @")[-1].strip().strip("-").strip()
            try:
                fmt = "%H:%M:%S.%f" if "." in time_str else "%H:%M:%S"
                status_time = datetime.strptime(time_str, fmt).time()
            except ValueError:
                status_time = None
            break
    if anchor_date and status_time:
        return datetime.combine(anchor_date, status_time)
    return None


def _iter_market_rows(path: str):
    with open(path, "r", encoding="utf-8") as f:
        header = f.readline().strip("\n")
        if not header:
            return
        cols = header.split(",")
        idx = {c: i for i, c in enumerate(cols)}
        for line in f:
            if not line.strip():
                continue
            parts = line.strip("\n").split(",")
            ts_idx = idx.get("timestamp", -1)
            ticker_idx = idx.get("market_ticker", -1)
            if ts_idx >= len(parts) or ticker_idx >= len(parts):
                continue
            ts = parts[ts_idx]
            dt = _parse_time(ts)
            if dt is None:
                continue
            ticker = parts[ticker_idx]
            last_trade = None
            lt_idx = idx.get("last_trade_price")
            if lt_idx is not None and lt_idx < len(parts):
                last_trade = parts[lt_idx]
            elif len(parts) > len(cols):
                last_trade = parts[-1]
            yield {
                "time": dt,
                "ticker": ticker,
                "best_yes_bid": parts[idx.get("best_yes_bid", -1)] if idx.get("best_yes_bid", -1) < len(parts) else None,
                "best_no_bid": parts[idx.get("best_no_bid", -1)] if idx.get("best_no_bid", -1) < len(parts) else None,
                "implied_no_ask": parts[idx.get("implied_no_ask", -1)] if idx.get("implied_no_ask", -1) < len(parts) else None,
                "implied_yes_ask": parts[idx.get("implied_yes_ask", -1)] if idx.get("implied_yes_ask", -1) < len(parts) else None,
                "last_trade": last_trade,
            }


def _load_positions(path: str) -> tuple[float, dict]:
    data = json.load(open(path, "r", encoding="utf-8"))
    return float(data.get("cash") or 0.0), data.get("positions") or {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare per-ticker market value between live and backtest positions."
    )
    parser.add_argument("--live-positions", default=os.path.join("vm_logs", "unified_engine_out", "unified_positions.json"))
    parser.add_argument("--backtest-positions", default=os.path.join("unified_engine_out_snapshot_live", "unified_positions.json"))
    parser.add_argument("--market-dir", default=os.path.join("vm_logs", "market_logs"))
    parser.add_argument("--output-log", default=os.path.join("server_mirror", "output.log"))
    parser.add_argument("--asof", default="", help="Override timestamp (YYYY-mm-dd HH:MM:SS)")
    parser.add_argument("--fallback", default="best_yes_bid", choices=["best_yes_bid", "implied_yes_ask", "mid_implied"])
    args = parser.parse_args()

    if args.asof:
        try:
            asof = datetime.strptime(args.asof, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            asof = _parse_time(args.asof)
    else:
        asof = _latest_status_time(args.output_log)
    if not asof:
        raise SystemExit("No status time found; pass --asof.")

    live_cash, live_positions = _load_positions(args.live_positions)
    back_cash, back_positions = _load_positions(args.backtest_positions)

    all_tickers = set(live_positions) | set(back_positions)
    latest = {}
    for name in os.listdir(args.market_dir):
        if not (name.startswith("market_data_") and name.endswith(".csv")):
            continue
        path = os.path.join(args.market_dir, name)
        for row in _iter_market_rows(path):
            if row["time"] > asof:
                continue
            if row["ticker"] not in all_tickers:
                continue
            prev = latest.get(row["ticker"])
            if prev is None or row["time"] > prev["time"]:
                latest[row["ticker"]] = row

    print(f"As of: {asof.isoformat()}")
    print("ticker,price,price_source,live_qty,live_value,back_qty,back_value,diff_value,last_trade_ts")
    live_total = 0.0
    back_total = 0.0
    for ticker in sorted(all_tickers):
        row = latest.get(ticker)
        if not row:
            continue
        last_trade = _parse_float(row.get("last_trade"))
        yb = _parse_float(row.get("best_yes_bid"))
        ya = _parse_float(row.get("implied_yes_ask"))
        na = _parse_float(row.get("implied_no_ask"))

        price = None
        price_source = None
        if last_trade is not None:
            price = last_trade
            price_source = "last_trade"
        else:
            if args.fallback == "best_yes_bid":
                price = yb
                price_source = "best_yes_bid"
            elif args.fallback == "implied_yes_ask":
                price = ya
                price_source = "implied_yes_ask"
            elif args.fallback == "mid_implied":
                if ya is not None and na is not None:
                    price = (ya + (100.0 - na)) / 2.0
                    price_source = "mid_implied"

        if price is None:
            continue

        live_pos = live_positions.get(ticker, {})
        back_pos = back_positions.get(ticker, {})
        live_qty = int(live_pos.get("yes") or 0) + int(live_pos.get("no") or 0)
        back_qty = int(back_pos.get("yes") or 0) + int(back_pos.get("no") or 0)

        live_value = live_qty * (price / 100.0)
        back_value = back_qty * (price / 100.0)
        diff_value = live_value - back_value

        live_total += live_value
        back_total += back_value

        print(
            f"{ticker},{price},{price_source},{live_qty},{live_value:.2f},{back_qty},{back_value:.2f},{diff_value:.2f},{row['time'].isoformat()}"
        )

    live_equity = live_cash + live_total
    back_equity = back_cash + back_total
    print(f"Live total market value: {live_total:.2f} (cash {live_cash:.2f} equity {live_equity:.2f})")
    print(f"Backtest total market value: {back_total:.2f} (cash {back_cash:.2f} equity {back_equity:.2f})")
    print(f"Equity diff (live - backtest): {live_equity - back_equity:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
