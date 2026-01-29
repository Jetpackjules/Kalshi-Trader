import os
import sys
import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Ensure repo root is on sys.path so `server_mirror` imports work when executed from `tools/`.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from server_mirror.unified_engine.adapters import (  # noqa: E402
    LiveAdapter,
    create_headers,
    API_URL,
    calculate_convex_fee,
)


def _parse_dt_utc(ts: str) -> datetime | None:
    if not ts:
        return None
    s = ts.strip()
    # Kalshi uses "...Z"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fetch_fills(adapter: LiveAdapter, *, limit: int = 200):
    cursor = None
    while True:
        path = f"/trade-api/v2/portfolio/fills?limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        headers = create_headers(adapter.private_key, "GET", path)
        resp = adapter._session.get(API_URL + path, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        fills = data.get("fills", [])
        if not fills:
            return
        for f in fills:
            yield f
        cursor = data.get("cursor")
        if not cursor:
            return


def main() -> int:
    ap = argparse.ArgumentParser(description="Estimate Kalshi fees paid from fills for the current local day.")
    ap.add_argument("--tz", default="America/Los_Angeles", help="Local timezone for 'today' (default: America/Los_Angeles)")
    ap.add_argument("--date", default=None, help="Local date YYYY-MM-DD to compute fees for (default: today in --tz)")
    ap.add_argument("--limit", type=int, default=200, help="Fills page size (default: 200)")
    args = ap.parse_args()

    tz = ZoneInfo(args.tz)
    now_local = datetime.now(tz)
    if args.date:
        y, m, d = (int(x) for x in args.date.split("-"))
        start_local = datetime(y, m, d, 0, 0, 0, tzinfo=tz)
    else:
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local.replace(hour=23, minute=59, second=59, microsecond=999999)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    adapter = LiveAdapter(key_path="keys/kalshi_prod_private_key.pem")

    fills = []
    maker = 0
    taker = 0
    contracts = 0
    fee_total = 0.0

    # Fills are newest-first; stop once we fall before start_utc.
    for f in _fetch_fills(adapter, limit=args.limit):
        ts = _parse_dt_utc(f.get("created_time", ""))
        if ts is None:
            continue
        if ts < start_utc:
            break
        if ts > end_utc:
            continue

        side = f.get("side")
        qty = int(f.get("count") or 0)
        if qty <= 0:
            continue
        price = f.get("yes_price") if side == "yes" else f.get("no_price")
        if price is None:
            continue

        fills.append(f)
        contracts += qty
        fee_total += calculate_convex_fee(float(price), qty)
        if f.get("is_taker"):
            taker += 1
        else:
            maker += 1

    print(f"local_day: {start_local.strftime('%Y-%m-%d')} ({args.tz})")
    print(f"fills: {len(fills)}")
    print(f"contracts: {contracts}")
    print(f"maker_fills: {maker}")
    print(f"taker_fills: {taker}")
    print(f"fee_est_usd: {fee_total:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
