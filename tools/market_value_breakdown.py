import argparse
import base64
import json
import os
import re
import time
from datetime import datetime

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API_URL_DEFAULT = "https://api.elections.kalshi.com"
KEY_ID_DEFAULT = "ab739236-261e-4130-bd46-2c0330d0bf57"


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


def _sign_pss_text(private_key, text: str) -> str:
    message = text.encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _create_headers(private_key, key_id: str, method: str, path: str) -> dict:
    timestamp = str(int(time.time() * 1000))
    msg_string = timestamp + method + path.split("?")[0]
    signature = _sign_pss_text(private_key, msg_string)
    return {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }


def _api_get_json(private_key, key_id: str, api_url: str, path: str, params: dict | None = None) -> dict:
    headers = _create_headers(private_key, key_id, "GET", path)
    resp = requests.get(api_url + path, headers=headers, params=params, timeout=20)
    if resp.status_code != 200:
        raise SystemExit(f"Kalshi API error {resp.status_code}: {resp.text}")
    data = resp.json()
    if not isinstance(data, dict):
        raise SystemExit("Unexpected API response.")
    return data


def _load_private_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _load_positions_from_api(private_key, key_id: str, api_url: str) -> tuple[float, dict]:
    balance = _api_get_json(private_key, key_id, api_url, "/trade-api/v2/portfolio/balance")
    cash = float(balance.get("balance", 0.0)) / 100.0

    data = _api_get_json(private_key, key_id, api_url, "/trade-api/v2/portfolio/positions")
    positions = {}
    for p in data.get("market_positions", []):
        ticker = p.get("ticker")
        raw_qty = int(p.get("position", 0) or 0)
        if not ticker or raw_qty == 0:
            continue
        entry = positions.setdefault(ticker, {"yes": 0, "no": 0})
        if raw_qty > 0:
            entry["yes"] = abs(raw_qty)
        else:
            entry["no"] = abs(raw_qty)
    return cash, positions


def _load_market_from_api(private_key, key_id: str, api_url: str, ticker: str) -> dict:
    data = _api_get_json(private_key, key_id, api_url, f"/trade-api/v2/markets/{ticker}")
    market = data.get("market")
    if not market and isinstance(data.get("markets"), list) and data["markets"]:
        market = data["markets"][0]
    if not market and isinstance(data, dict):
        market = data
    return market or {}


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute per-ticker market value from logs.")
    parser.add_argument("--snapshot-dir", default=os.path.join("vm_logs", "snapshots"))
    parser.add_argument("--snapshot", default="")
    parser.add_argument("--market-dir", default=os.path.join("vm_logs", "market_logs"))
    parser.add_argument("--output-log", default=os.path.join("server_mirror", "output.log"))
    parser.add_argument("--asof", default="", help="Override timestamp (YYYY-mm-dd HH:MM:SS)")
    parser.add_argument("--fallback", default="best_yes_bid", choices=["best_yes_bid", "implied_yes_ask", "mid_implied"])
    parser.add_argument("--use-api", action="store_true", help="Use live Kalshi API prices (current only).")
    parser.add_argument("--key-file", default=os.path.join("keys", "kalshi_prod_private_key.pem"))
    parser.add_argument("--key-id", default=KEY_ID_DEFAULT)
    parser.add_argument("--api-url", default=API_URL_DEFAULT)
    args = parser.parse_args()

    snapshot_path = None
    cash = None
    if args.use_api:
        if args.asof:
            print("NOTE: --use-api ignores --asof; Kalshi API only provides current prices.")
        private_key = _load_private_key(args.key_file)
        cash, positions = _load_positions_from_api(private_key, args.key_id, args.api_url)
        if not positions:
            raise SystemExit("API returned no positions.")
    else:
        snapshot_path = args.snapshot or _latest_snapshot(args.snapshot_dir)
        if not snapshot_path:
            raise SystemExit("No snapshot found.")

        snap = json.load(open(snapshot_path, "r", encoding="utf-8"))
        positions = snap.get("positions") or {}
        if not positions:
            raise SystemExit("Snapshot has no positions.")

    if args.use_api:
        asof = datetime.now()
    else:
        if args.asof:
            try:
                asof = datetime.strptime(args.asof, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                asof = _parse_time(args.asof)
        else:
            asof = _latest_status_time(args.output_log)
        if not asof:
            raise SystemExit("No status time found; pass --asof.")

    latest = {}
    if args.use_api:
        for ticker in positions:
            market = _load_market_from_api(private_key, args.key_id, args.api_url, ticker)
            latest[ticker] = {
                "time": datetime.now(),
                "ticker": ticker,
                "best_yes_bid": market.get("yes_bid") or market.get("best_yes_bid"),
                "best_no_bid": market.get("no_bid") or market.get("best_no_bid"),
                "implied_no_ask": market.get("no_ask") or market.get("implied_no_ask"),
                "implied_yes_ask": market.get("yes_ask") or market.get("implied_yes_ask"),
                "last_trade": market.get("last_price")
                or market.get("last_trade_price")
                or market.get("last_trade_price_yes"),
            }
    else:
        for name in os.listdir(args.market_dir):
            if not (name.startswith("market_data_") and name.endswith(".csv")):
                continue
            path = os.path.join(args.market_dir, name)
            for row in _iter_market_rows(path):
                if row["time"] > asof:
                    continue
                if row["ticker"] not in positions:
                    continue
                prev = latest.get(row["ticker"])
                if prev is None or row["time"] > prev["time"]:
                    latest[row["ticker"]] = row

    total = 0.0
    if snapshot_path:
        print(f"Snapshot: {os.path.basename(snapshot_path)}")
    print(f"As of: {asof.isoformat()}")
    print("ticker,qty,last_trade,best_yes_bid,implied_yes_ask,used_price,used_source,value,last_trade_ts")
    for ticker, pos in sorted(positions.items()):
        row = latest.get(ticker)
        if not row:
            continue
        yes_qty = int(pos.get("yes") or 0)
        no_qty = int(pos.get("no") or 0)

        last_trade = _parse_float(row.get("last_trade"))
        yb = _parse_float(row.get("best_yes_bid"))
        ya = _parse_float(row.get("implied_yes_ask"))
        na = _parse_float(row.get("implied_no_ask"))

        used_price = None
        used_source = None
        if last_trade is not None:
            used_price = last_trade
            used_source = "last_trade"
        else:
            if args.fallback == "best_yes_bid":
                used_price = yb
                used_source = "best_yes_bid"
            elif args.fallback == "implied_yes_ask":
                used_price = ya
                used_source = "implied_yes_ask"
            elif args.fallback == "mid_implied":
                if ya is not None and na is not None:
                    used_price = (ya + (100.0 - na)) / 2.0
                    used_source = "mid_implied"

        if used_price is None:
            continue

        value = yes_qty * (used_price / 100.0) + no_qty * ((100.0 - used_price) / 100.0)
        total += value

        print(
            f"{ticker},{yes_qty + no_qty},{last_trade},{yb},{ya},{used_price},{used_source},{value:.2f},{row['time'].isoformat()}"
        )

    print(f"Total market value: {total:.2f}")
    if cash is not None:
        print(f"Cash: {cash:.2f} (equity {cash + total:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
