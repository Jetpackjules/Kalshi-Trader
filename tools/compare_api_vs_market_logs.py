import argparse
import base64
import csv
import os
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


def _coerce_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
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


def _api_get_json(private_key, key_id: str, api_url: str, path: str) -> dict:
    headers = _create_headers(private_key, key_id, "GET", path)
    resp = requests.get(api_url + path, headers=headers, timeout=20)
    if resp.status_code != 200:
        raise SystemExit(f"Kalshi API error {resp.status_code}: {resp.text}")
    data = resp.json()
    if not isinstance(data, dict):
        raise SystemExit("Unexpected API response.")
    return data


def _load_private_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _select_market_files(market_dir: str, latest_files: int) -> list[str]:
    files = []
    for name in os.listdir(market_dir):
        if name.startswith("market_data_") and name.endswith(".csv"):
            files.append(os.path.join(market_dir, name))
    if latest_files and latest_files > 0:
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        files = files[:latest_files]
    return files


def _latest_market_rows(market_dir: str, latest_files: int) -> dict:
    latest = {}
    for path in _select_market_files(market_dir, latest_files):
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames or []
            for row in reader:
                ts = _parse_time(row.get("timestamp") or "")
                if ts is None:
                    continue
                ticker = (row.get("market_ticker") or "").strip()
                if not ticker:
                    continue
                prev = latest.get(ticker)
                if prev is not None and ts <= prev["time"]:
                    continue
                last_trade = row.get("last_trade_price")
                if last_trade in (None, "") and row.get(None):
                    extras = row.get(None)
                    last_trade = extras[-1] if isinstance(extras, list) else extras
                latest[ticker] = {
                    "time": ts,
                    "best_yes_bid": row.get("best_yes_bid"),
                    "implied_yes_ask": row.get("implied_yes_ask"),
                    "last_trade": last_trade,
                    "has_last_trade_col": "last_trade_price" in cols or len(row) > len(cols),
                }
    return latest


def _fetch_market(private_key, key_id: str, api_url: str, ticker: str) -> dict:
    data = _api_get_json(private_key, key_id, api_url, f"/trade-api/v2/markets/{ticker}")
    market = data.get("market")
    if not market and isinstance(data.get("markets"), list) and data["markets"]:
        market = data["markets"][0]
    if not market and isinstance(data, dict):
        market = data
    return market or {}


def _write_rows(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    header = list(rows[0].keys())
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _run_once(args) -> None:
    private_key = _load_private_key(args.key_file)
    latest = _latest_market_rows(args.market_dir, args.latest_files)
    if not latest:
        print("No market rows found.")
        return

    tickers = sorted(latest.keys())
    if args.limit and args.limit > 0:
        tickers = tickers[: args.limit]

    now = datetime.utcnow().isoformat()
    output_rows = []
    for ticker in tickers:
        log_row = latest[ticker]
        market = _fetch_market(private_key, args.key_id, args.api_url, ticker)
        api_last = market.get("last_price")
        api_yes_bid = market.get("yes_bid")
        api_yes_ask = market.get("yes_ask")
        output_rows.append(
            {
                "run_time_utc": now,
                "ticker": ticker,
                "log_time": log_row["time"].isoformat(),
                "log_last_trade": log_row["last_trade"],
                "log_yes_bid": log_row["best_yes_bid"],
                "log_yes_ask": log_row["implied_yes_ask"],
                "api_last_price": api_last,
                "api_yes_bid": api_yes_bid,
                "api_yes_ask": api_yes_ask,
                "diff_last": (
                    _coerce_float(api_last) - _coerce_float(log_row["last_trade"])
                    if _coerce_float(api_last) is not None and _coerce_float(log_row["last_trade"]) is not None
                    else ""
                ),
                "diff_yes_bid": (
                    _coerce_float(api_yes_bid) - _coerce_float(log_row["best_yes_bid"])
                    if _coerce_float(api_yes_bid) is not None and _coerce_float(log_row["best_yes_bid"]) is not None
                    else ""
                ),
                "diff_yes_ask": (
                    _coerce_float(api_yes_ask) - _coerce_float(log_row["implied_yes_ask"])
                    if _coerce_float(api_yes_ask) is not None and _coerce_float(log_row["implied_yes_ask"]) is not None
                    else ""
                ),
            }
        )

    _write_rows(args.out, output_rows)
    print(f"Wrote {len(output_rows)} rows to {args.out}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Kalshi API market data vs latest local market_logs ticks."
    )
    parser.add_argument("--market-dir", default=os.path.join("vm_logs", "market_logs"))
    parser.add_argument("--out", default=os.path.join("vm_logs", "market_discrepancies.csv"))
    parser.add_argument("--key-file", default=os.path.join("keys", "kalshi_prod_private_key.pem"))
    parser.add_argument("--key-id", default=KEY_ID_DEFAULT)
    parser.add_argument("--api-url", default=API_URL_DEFAULT)
    parser.add_argument("--limit", type=int, default=0, help="Limit number of tickers per run")
    parser.add_argument(
        "--latest-files",
        type=int,
        default=0,
        help="Only scan the N most recently modified market_data_*.csv files",
    )
    parser.add_argument("--interval-s", type=int, default=0, help="Poll interval (0=run once)")
    parser.add_argument("--iterations", type=int, default=0, help="Iterations when interval > 0 (0=loop forever)")
    args = parser.parse_args()

    if args.interval_s and args.interval_s > 0:
        count = 0
        while True:
            _run_once(args)
            count += 1
            if args.iterations and count >= args.iterations:
                break
            time.sleep(args.interval_s)
    else:
        _run_once(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
