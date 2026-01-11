import argparse
import base64
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


API_URL = os.environ.get("KALSHI_API_URL", "https://api.elections.kalshi.com")
DEFAULT_KEY_PATH = os.path.join("keys", "kalshi_prod_private_key.pem")
LIVE_TRADER_V4_PATH = os.path.join("server_mirror", "live_trader_v4.py")


def load_key_id() -> str:
    env_key = os.environ.get("KALSHI_KEY_ID")
    if env_key:
        return env_key

    if os.path.exists(LIVE_TRADER_V4_PATH):
        with open(LIVE_TRADER_V4_PATH, "r", encoding="utf-8") as f:
            text = f.read()
        match = re.search(r'^\s*KEY_ID\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match:
            return match.group(1)

    raise RuntimeError("Missing KALSHI_KEY_ID (env) and could not find KEY_ID in live_trader_v4.py.")


def load_private_key():
    pem_env = os.environ.get("KALSHI_PRIVATE_KEY_PEM")
    if pem_env:
        return serialization.load_pem_private_key(pem_env.encode("utf-8"), password=None)

    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", DEFAULT_KEY_PATH)
    if not os.path.exists(key_path):
        raise RuntimeError(f"Private key not found at {key_path}. Set KALSHI_PRIVATE_KEY_PATH or KALSHI_PRIVATE_KEY_PEM.")

    with open(key_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def sign_pss_text(private_key, text: str) -> str:
    message = text.encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def create_headers(private_key, key_id: str, method: str, path: str) -> dict:
    timestamp = str(int(time.time() * 1000))
    msg_string = timestamp + method + path.split("?")[0]
    signature = sign_pss_text(private_key, msg_string)
    return {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }


def get_today_bounds_local():
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def to_unix_seconds(dt: datetime) -> int:
    return int(dt.timestamp())


def _parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _parse_trade_time(value: str, tz_offset_hours: float) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
    tz = timezone(timedelta(hours=tz_offset_hours))
    return dt.replace(tzinfo=tz)


def _load_trades(path: str, tz_offset_hours: float) -> list[dict]:
    trades = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row.get("time") or row.get("timestamp")
            if not ts:
                continue
            try:
                dt = _parse_trade_time(ts, tz_offset_hours)
            except Exception:
                continue
            action = (row.get("action") or "").upper()
            side = "yes" if action.endswith("_YES") else "no"
            trades.append(
                {
                    "time": dt,
                    "action": action,
                    "side": side,
                    "ticker": row.get("ticker") or "",
                    "price": float(row.get("price") or 0.0),
                    "qty": int(row.get("qty") or 0),
                    "order_id": (row.get("order_id") or "").strip() or None,
                }
            )
    trades.sort(key=lambda x: x["time"])
    return trades


def _bounds_from_trades(trades: list[dict], pad_seconds: int) -> tuple[int, int] | None:
    if not trades:
        return None
    start = trades[0]["time"] - timedelta(seconds=pad_seconds)
    end = trades[-1]["time"] + timedelta(seconds=pad_seconds)
    return to_unix_seconds(start), to_unix_seconds(end)


def _normalize_fill(fill: dict) -> dict:
    side = (fill.get("side") or "").lower()
    price = fill.get("yes_price") if side == "yes" else fill.get("no_price")
    return {
        "time": datetime.fromtimestamp(fill.get("ts", 0), tz=timezone.utc),
        "ticker": fill.get("ticker") or fill.get("market_ticker") or "",
        "side": side,
        "price": float(price) if price is not None else None,
        "qty": int(fill.get("count") or 0),
        "order_id": fill.get("order_id"),
        "fill_id": fill.get("fill_id") or fill.get("trade_id"),
    }


def _compare_trades_to_fills(
    trades: list[dict],
    fills: list[dict],
    match_window_seconds: int,
    tz_offset_hours: float,
    collect_delays: bool = False,
) -> dict:
    fills_by_order: dict[str, list[dict]] = {}
    available_fills = []
    for raw in fills:
        f = _normalize_fill(raw)
        available_fills.append(f)
        if f["order_id"]:
            fills_by_order.setdefault(f["order_id"], []).append(f)

    for order_id in fills_by_order:
        fills_by_order[order_id].sort(key=lambda x: x["time"])

    matched = []
    unmatched = []
    matched_delays = []
    window = timedelta(seconds=match_window_seconds)

    for tr in trades:
        if tr["order_id"] and tr["order_id"] in fills_by_order:
            f_list = fills_by_order[tr["order_id"]]
            first_fill = f_list[0]
            delay = (first_fill["time"] - tr["time"]).total_seconds()
            matched_delays.append(delay)
            matched.append(
                {
                    "order_id": tr["order_id"],
                    "ticker": tr["ticker"],
                    "side": tr["side"],
                    "order_time": tr["time"].isoformat(),
                    "first_fill_time": first_fill["time"].isoformat(),
                    "delay_seconds": delay,
                    "filled_qty": sum(f["qty"] for f in f_list),
                    "order_qty": tr["qty"],
                }
            )
            for f in f_list:
                if f in available_fills:
                    available_fills.remove(f)
            continue

        # Fallback match by ticker/side/price/qty within window
        candidates = [
            f for f in available_fills
            if f["ticker"] == tr["ticker"]
            and f["side"] == tr["side"]
            and f["price"] == tr["price"]
            and f["qty"] == tr["qty"]
            and abs(f["time"] - tr["time"]) <= window
        ]
        if candidates:
            candidates.sort(key=lambda f: abs(f["time"] - tr["time"]))
            f = candidates[0]
            available_fills.remove(f)
            delay = (f["time"] - tr["time"]).total_seconds()
            matched_delays.append(delay)
            matched.append(
                {
                    "order_id": tr["order_id"],
                    "ticker": tr["ticker"],
                    "side": tr["side"],
                    "order_time": tr["time"].isoformat(),
                    "first_fill_time": f["time"].isoformat(),
                    "delay_seconds": delay,
                    "filled_qty": f["qty"],
                    "order_qty": tr["qty"],
                }
            )
        else:
            unmatched.append(
                {
                    "order_id": tr["order_id"],
                    "ticker": tr["ticker"],
                    "side": tr["side"],
                    "order_time": tr["time"].isoformat(),
                    "order_qty": tr["qty"],
                }
            )

    delays = [m["delay_seconds"] for m in matched]
    delays_sorted = sorted(delays)
    def pct(p):
        if not delays_sorted:
            return None
        idx = int((p / 100.0) * (len(delays_sorted) - 1))
        return delays_sorted[idx]

    buckets = {
        "<=1s": sum(1 for d in delays if d <= 1),
        "<=5s": sum(1 for d in delays if d <= 5),
        "<=30s": sum(1 for d in delays if d <= 30),
        "<=60s": sum(1 for d in delays if d <= 60),
        "<=300s": sum(1 for d in delays if d <= 300),
        ">300s": sum(1 for d in delays if d > 300),
    }

    result = {
        "trade_tz_offset_hours": tz_offset_hours,
        "total_trades": len(trades),
        "matched": len(matched),
        "unmatched": len(unmatched),
        "delay_seconds": {
            "min": min(delays) if delays else None,
            "p50": pct(50),
            "p90": pct(90),
            "max": max(delays) if delays else None,
            "buckets": buckets,
        },
    }
    if collect_delays:
        result["matched_delays"] = matched_delays
    return result


def fetch_todays_fills(
    min_ts: int | None = None,
    max_ts: int | None = None,
    page_limit: int = 200,
    max_pages: int = 0,
):
    key_id = load_key_id()
    private_key = load_private_key()

    if min_ts is None or max_ts is None:
        start_dt, end_dt = get_today_bounds_local()
        min_ts = to_unix_seconds(start_dt)
        max_ts = to_unix_seconds(end_dt)
    else:
        start_dt = datetime.fromtimestamp(min_ts, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(max_ts, tz=timezone.utc)

    path = "/trade-api/v2/portfolio/fills"
    url = f"{API_URL}{path}"

    all_fills = []
    cursor = None

    page_count = 0
    while True:
        params = {
            "min_ts": min_ts,
            "max_ts": max_ts,
            "limit": page_limit,
        }
        if cursor:
            params["cursor"] = cursor

        headers = create_headers(private_key, key_id, "GET", path)
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"Kalshi API error {resp.status_code}: {resp.text}")

        payload = resp.json()
        fills = payload.get("fills", [])
        all_fills.extend(fills)

        cursor = payload.get("cursor")
        page_count += 1
        if max_pages and page_count >= max_pages:
            break
        if not cursor:
            break

    return {
        "date_local": start_dt.strftime("%Y-%m-%d"),
        "start_local": start_dt.isoformat(),
        "end_local": end_dt.isoformat(),
        "count": len(all_fills),
        "fills": all_fills,
    }


def main():
    try:
        parser = argparse.ArgumentParser(description="Fetch Kalshi fills and optionally compare to order placements.")
        parser.add_argument("--start", default="", help="ISO start time (overrides today)")
        parser.add_argument("--end", default="", help="ISO end time (overrides today)")
        parser.add_argument("--min-ts", type=int, default=None, help="Unix seconds start (overrides today)")
        parser.add_argument("--max-ts", type=int, default=None, help="Unix seconds end (overrides today)")
        parser.add_argument("--trades-csv", default="", help="Path to trades.csv to compare timing")
        parser.add_argument("--pad-seconds", type=int, default=3600, help="Padding around trades range")
        parser.add_argument("--match-window-seconds", type=int, default=300, help="Fallback match window")
        parser.add_argument("--trade-tz-offset", type=float, default=0.0, help="Hours offset for trades timestamps")
        parser.add_argument("--lookback-hours", type=float, default=0.0, help="If set (and no other bounds), fetch from now - hours")
        parser.add_argument("--lookback-days", type=float, default=0.0, help="If set (and no other bounds), fetch from now - days")
        parser.add_argument("--page-limit", type=int, default=200, help="API page size")
        parser.add_argument("--max-pages", type=int, default=0, help="Cap number of pages (0 = no cap)")
        parser.add_argument("--write-latency-model", default="", help="Write latency model JSON to this path")
        args = parser.parse_args()

        trades = []
        min_ts = args.min_ts
        max_ts = args.max_ts

        if args.start and args.end:
            start_dt = _parse_dt(args.start)
            end_dt = _parse_dt(args.end)
            min_ts = to_unix_seconds(start_dt)
            max_ts = to_unix_seconds(end_dt)

        if args.trades_csv:
            trades = _load_trades(args.trades_csv, args.trade_tz_offset)
            if min_ts is None or max_ts is None:
                bounds = _bounds_from_trades(trades, args.pad_seconds)
                if bounds:
                    min_ts, max_ts = bounds

        if min_ts is None or max_ts is None:
            lookback_hours = args.lookback_hours + (args.lookback_days * 24.0)
            if lookback_hours > 0:
                end_dt = datetime.now().astimezone()
                start_dt = end_dt - timedelta(hours=lookback_hours)
                min_ts = to_unix_seconds(start_dt)
                max_ts = to_unix_seconds(end_dt)

        result = fetch_todays_fills(
            min_ts=min_ts,
            max_ts=max_ts,
            page_limit=args.page_limit,
            max_pages=args.max_pages,
        )
        if trades:
            comparison = _compare_trades_to_fills(
                trades,
                result["fills"],
                args.match_window_seconds,
                args.trade_tz_offset,
                collect_delays=bool(args.write_latency_model),
            )
            result["comparison"] = comparison
            if args.write_latency_model:
                delays = comparison.get("matched_delays", [])
                model = {
                    "generated_at": datetime.now().astimezone().isoformat(),
                    "match_window_seconds": args.match_window_seconds,
                    "trade_tz_offset_hours": args.trade_tz_offset,
                    "total_trades": comparison.get("total_trades", 0),
                    "matched": comparison.get("matched", 0),
                    "delays_seconds": delays,
                    "clamped_delays": [max(0.0, d) for d in delays],
                    "stats": comparison.get("delay_seconds", {}),
                }
                with open(args.write_latency_model, "w", encoding="utf-8") as f:
                    json.dump(model, f, indent=2)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
