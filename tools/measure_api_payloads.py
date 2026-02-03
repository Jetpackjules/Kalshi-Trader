from __future__ import annotations

import argparse
import statistics
import time
from datetime import datetime, timezone
from dataclasses import dataclass

import requests
from cryptography.hazmat.primitives import serialization

from server_mirror.unified_engine.adapters import create_headers, API_URL


@dataclass
class Sample:
    path: str
    status: int
    bytes: int


def _load_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _fetch(session: requests.Session, key, api_url: str, path: str) -> Sample:
    headers = create_headers(key, "GET", path)
    resp = session.get(api_url + path, headers=headers, timeout=20)
    return Sample(path=path, status=resp.status_code, bytes=len(resp.content))


def _fetch_json(session: requests.Session, key, api_url: str, path: str) -> tuple[Sample, dict]:
    headers = create_headers(key, "GET", path)
    resp = session.get(api_url + path, headers=headers, timeout=20)
    data = {}
    if resp.status_code == 200:
        try:
            data = resp.json()
        except Exception:
            data = {}
    return Sample(path=path, status=resp.status_code, bytes=len(resp.content)), data


def _parse_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _summarize(label: str, samples: list[Sample]) -> None:
    sizes = [s.bytes for s in samples]
    ok = [s for s in samples if s.status == 200]
    if not sizes:
        print(f"{label}: no samples")
        return
    avg = statistics.mean(sizes)
    p95 = statistics.quantiles(sizes, n=20)[-1] if len(sizes) >= 20 else max(sizes)
    status_set = sorted({s.status for s in samples})
    print(f"{label}: avg={avg:.0f}B p95={p95:.0f}B statuses={status_set} ok={len(ok)}/{len(samples)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure Kalshi API payload sizes.")
    parser.add_argument("--key-file", required=True, help="Path to Kalshi private key PEM")
    parser.add_argument("--api-url", default=API_URL, help="Base API URL")
    parser.add_argument("--repeats", type=int, default=5, help="Number of samples per endpoint")
    parser.add_argument("--fills-limit", type=int, default=200, help="Fills limit param")
    parser.add_argument("--poll-fills", action="store_true", help="Poll fills endpoint with cursor")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Seconds between fill polls")
    parser.add_argument("--poll-count", type=int, default=10, help="Number of fill polls")
    parser.add_argument("--poll-mode", choices=["cursor", "newest", "min_ts"], default="newest", help="Polling mode for fills")
    args = parser.parse_args()

    key = _load_key(args.key_file)
    session = requests.Session()

    endpoints = [
        ("orders_all", "/trade-api/v2/portfolio/orders"),
        ("orders_open", "/trade-api/v2/portfolio/orders?status=open"),
        ("fills", f"/trade-api/v2/portfolio/fills?limit={args.fills_limit}"),
    ]

    results: dict[str, list[Sample]] = {name: [] for name, _ in endpoints}

    for _ in range(max(1, args.repeats)):
        for name, path in endpoints:
            sample = _fetch(session, key, args.api_url, path)
            results[name].append(sample)

    print("Payload size summary (bytes):")
    for name, _ in endpoints:
        _summarize(name, results[name])

    # Quick ratios for convenience.
    if results["orders_all"] and results["orders_open"]:
        avg_all = statistics.mean(s.bytes for s in results["orders_all"])
        avg_open = statistics.mean(s.bytes for s in results["orders_open"])
        if avg_open > 0:
            print(f"orders_all / orders_open ~= {avg_all/avg_open:.1f}x")

    if not args.poll_fills:
        return

    print("")
    print(f"Polling fills ({args.poll_mode} mode):")
    cursor = None
    last_seen_time = None
    last_seen_ids: set[str] = set()
    for i in range(max(1, args.poll_count)):
        path = f"/trade-api/v2/portfolio/fills?limit={args.fills_limit}"
        if args.poll_mode == "cursor" and cursor:
            path += f"&cursor={cursor}"
        elif args.poll_mode == "min_ts" and last_seen_time is not None:
            min_ts = int(last_seen_time.timestamp())
            path += f"&min_ts={min_ts}"
        sample, data = _fetch_json(session, key, args.api_url, path)
        new_cursor = data.get("cursor")
        fills = data.get("fills", []) if isinstance(data.get("fills", []), list) else []
        new_count = 0
        if args.poll_mode == "cursor":
            new_count = len(fills)
            cursor = new_cursor or cursor
        else:
            # Newest-first polling: dedupe by last seen timestamp + order_id
            fills_sorted = []
            for f in fills:
                ts = _parse_dt(f.get("created_time"))
                fills_sorted.append((ts, f))
            fills_sorted.sort(key=lambda x: (x[0] or datetime.min.replace(tzinfo=timezone.utc)))
            for ts, f in fills_sorted:
                if ts is None:
                    continue
                oid = str(f.get("order_id") or "")
                if last_seen_time is not None:
                    if ts < last_seen_time:
                        continue
                    if ts == last_seen_time and oid in last_seen_ids:
                        continue
                new_count += 1
                if last_seen_time is None or ts > last_seen_time:
                    last_seen_time = ts
                    last_seen_ids = set([oid]) if oid else set()
                elif ts == last_seen_time and oid:
                    last_seen_ids.add(oid)
            cursor = new_cursor or cursor
        print(f"poll {i+1}/{args.poll_count}: status={sample.status} bytes={sample.bytes} new_fills={new_count}")
        time.sleep(max(0.0, args.poll_interval))


if __name__ == "__main__":
    main()
