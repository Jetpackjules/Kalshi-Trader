import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

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


def fetch_todays_fills():
    key_id = load_key_id()
    private_key = load_private_key()

    start_dt, end_dt = get_today_bounds_local()
    min_ts = to_unix_seconds(start_dt)
    max_ts = to_unix_seconds(end_dt)

    path = "/trade-api/v2/portfolio/fills"
    url = f"{API_URL}{path}"

    all_fills = []
    cursor = None

    while True:
        params = {
            "min_ts": min_ts,
            "max_ts": max_ts,
            "limit": 200,
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
        result = fetch_todays_fills()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
