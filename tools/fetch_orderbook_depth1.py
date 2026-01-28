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


def _tickers_from_market_logs(market_dir: str, latest_files: int) -> list[str]:
    tickers = set()
    for path in _select_market_files(market_dir, latest_files):
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ticker = (row.get("market_ticker") or "").strip()
                    if ticker:
                        tickers.add(ticker)
        except FileNotFoundError:
            continue
    return sorted(tickers)


def _extract_level(levels):
    if not levels:
        return None, None
    first = levels[0]
    if isinstance(first, dict):
        price = first.get("price")
        if price is None:
            price = first.get("p") or first.get("price_cents")
        qty = first.get("quantity")
        if qty is None:
            qty = first.get("qty") or first.get("size")
        return price, qty
    if isinstance(first, (list, tuple)) and len(first) >= 2:
        return first[0], first[1]
    return None, None


def _extract_orderbook_levels(orderbook: dict, side: str) -> tuple:
    if not isinstance(orderbook, dict):
        return (None, None, None, None)
    side_book = orderbook.get(side)
    if isinstance(side_book, list):
        bid_price, bid_qty = _extract_level(side_book)
        return bid_price, bid_qty, None, None
    if isinstance(side_book, dict):
        bids = side_book.get("bids")
        asks = side_book.get("asks")
        bid_price, bid_qty = _extract_level(bids)
        ask_price, ask_qty = _extract_level(asks)
        return bid_price, bid_qty, ask_price, ask_qty
    return (None, None, None, None)


def _fetch_orderbook_depth1(private_key, key_id: str, api_url: str, ticker: str) -> dict:
    path = f"/trade-api/v2/markets/{ticker}/orderbook?depth=1"
    return _api_get_json(private_key, key_id, api_url, path)


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch depth=1 orderbook for tickers.")
    parser.add_argument("--market-dir", default=os.path.join("vm_logs", "market_logs"))
    parser.add_argument("--latest-files", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ticker", action="append", default=[], help="Ticker to fetch (repeatable)")
    parser.add_argument("--tickers-file", default="", help="Optional file with tickers (one per line)")
    parser.add_argument("--out", default=os.path.join("vm_logs", "orderbook_depth1.csv"))
    parser.add_argument("--key-file", default=os.path.join("keys", "kalshi_prod_private_key.pem"))
    parser.add_argument("--key-id", default=KEY_ID_DEFAULT)
    parser.add_argument("--api-url", default=API_URL_DEFAULT)
    args = parser.parse_args()

    tickers = list(args.ticker or [])
    if args.tickers_file:
        try:
            with open(args.tickers_file, "r", encoding="utf-8") as f:
                tickers.extend([line.strip() for line in f if line.strip()])
        except FileNotFoundError:
            pass
    if not tickers:
        tickers = _tickers_from_market_logs(args.market_dir, args.latest_files)
    if args.limit and args.limit > 0:
        tickers = tickers[: args.limit]

    if not tickers:
        print("No tickers found to query.")
        return 0

    private_key = _load_private_key(args.key_file)
    now = datetime.utcnow().isoformat()
    rows = []
    for ticker in tickers:
        data = _fetch_orderbook_depth1(private_key, args.key_id, args.api_url, ticker)
        orderbook = data.get("orderbook") or data.get("data") or data
        yes_bid_price, yes_bid_qty, yes_ask_price, yes_ask_qty = _extract_orderbook_levels(
            orderbook, "yes"
        )
        no_bid_price, no_bid_qty, no_ask_price, no_ask_qty = _extract_orderbook_levels(
            orderbook, "no"
        )
        implied_yes_ask = None
        implied_yes_ask_size = None
        implied_no_ask = None
        implied_no_ask_size = None
        if no_bid_price is not None:
            implied_yes_ask = 100 - float(no_bid_price)
            implied_yes_ask_size = no_bid_qty
        if yes_bid_price is not None:
            implied_no_ask = 100 - float(yes_bid_price)
            implied_no_ask_size = yes_bid_qty
        rows.append(
            {
                "run_time_utc": now,
                "ticker": ticker,
                "yes_bid_price": yes_bid_price,
                "yes_bid_qty": yes_bid_qty,
                "yes_ask_price": yes_ask_price,
                "yes_ask_qty": yes_ask_qty,
                "no_bid_price": no_bid_price,
                "no_bid_qty": no_bid_qty,
                "no_ask_price": no_ask_price,
                "no_ask_qty": no_ask_qty,
                "implied_yes_ask": implied_yes_ask,
                "implied_yes_ask_size": implied_yes_ask_size,
                "implied_no_ask": implied_no_ask,
                "implied_no_ask_size": implied_no_ask_size,
            }
        )

    _write_rows(args.out, rows)
    print(f"Wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
