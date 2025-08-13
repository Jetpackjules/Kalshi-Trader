import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


def _read_api_key_file(key_file_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """Parse `KALSHI_KEY.txt` to extract API key id and private key PEM.

    The script does not currently use the API key because public cached
    market endpoints generally suffice for market data. However, we parse it
    so the user can optionally extend auth easily later.
    """
    if not key_file_path.exists():
        return None, None

    api_key_id: Optional[str] = None
    private_key_pem_lines: List[str] = []
    in_pem = False

    for raw_line in key_file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("api key id"):
            # Next non-empty line should be key id
            continue
        if api_key_id is None and _looks_like_uuid(line):
            api_key_id = line
            continue

        # Private key block
        if "BEGIN" in line and "PRIVATE KEY" in line:
            in_pem = True
            private_key_pem_lines.append(line)
            continue
        if in_pem:
            private_key_pem_lines.append(line)
            if "END" in line and "PRIVATE KEY" in line:
                in_pem = False

    private_key_pem = None
    if private_key_pem_lines:
        # Join with newlines to reconstruct PEM
        private_key_pem = "\n".join(private_key_pem_lines) + ("\n" if not private_key_pem_lines[-1].endswith("\n") else "")

    return api_key_id, private_key_pem


def _looks_like_uuid(value: str) -> bool:
    # Very lightweight check for UUID-like string
    return len(value) >= 36 and value.count("-") >= 4


class KalshiClient:
    """Minimal client focused on public market data endpoints.

    Uses the production REST API base by default. This client avoids auth by
    preferring cached endpoints where available.
    """

    def __init__(self, base_url: str = "https://trading-api.kalshi.com/v1", timeout_s: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "kalshi-nyc-high-temp-history/1.0 (+https://kalshi.com)",
            }
        )

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=self.timeout_s)

        # Handle migration hint to elections domain
        if resp.status_code in (301, 302, 307, 308, 401):
            body = (resp.text or "").lower()
            if "api has been moved" in body and "api.elections.kalshi.com" in body:
                # Try likely new bases
                for new_base in (
                    "https://api.elections.kalshi.com/trade-api/v2",
                    "https://api.elections.kalshi.com/v1",
                    "https://trading-api.kalshi.com/trade-api/v2",
                ):
                    new_url = f"{new_base}/{path.lstrip('/')}"
                    try:
                        new_resp = self.session.get(new_url, params=params, timeout=self.timeout_s)
                    except Exception:
                        continue
                    if new_resp.status_code < 400:
                        # Update base for future requests
                        self.base_url = new_base
                        # Some servers may not set JSON content-type; try anyway
                        ct = new_resp.headers.get("content-type", "").lower()
                        if "json" in ct:
                            try:
                                return new_resp.json()
                            except Exception as exc:  # noqa: BLE001
                                raise RuntimeError(
                                    f"GET {new_url} invalid JSON: {exc} | body: {new_resp.text[:300]}"
                                ) from exc
                        else:
                            # Try to parse as JSON, else raise with body preview
                            try:
                                return new_resp.json()
                            except Exception as exc:  # noqa: BLE001
                                raise RuntimeError(
                                    f"GET {new_url} non-JSON ({ct}); body: {new_resp.text[:300]}"
                                ) from exc

        if resp.status_code >= 400:
            raise RuntimeError(f"GET {url} failed: {resp.status_code} {resp.text[:300]}")
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"GET {url} invalid JSON: {exc} | body: {resp.text[:300]}") from exc

    def list_markets_by_series(self, series_ticker: str, limit: int = 2000) -> List[Dict[str, Any]]:
        """Return markets for a series using cursor pagination.

        Tries `/markets` first; if the response includes a `cursor` or `next` token,
        continues fetching until `limit` reached or no more pages.
        """
        aggregated: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        page_size = 200

        while True:
            params: Dict[str, Any] = {"series_ticker": series_ticker, "limit": page_size}
            if cursor:
                params["cursor"] = cursor

            data = self._get("markets", params=params)

            # Heuristically locate markets list in response
            markets_list: Optional[List[Dict[str, Any]]] = None
            for candidate_key in ("markets", "data", "items", "results"):
                val = data.get(candidate_key)
                if isinstance(val, list):
                    markets_list = val
                    break
            if markets_list is None:
                # Some APIs return nested object like { data: { markets: [...] } }
                nested_data = data.get("data")
                if isinstance(nested_data, dict) and isinstance(nested_data.get("markets"), list):
                    markets_list = nested_data["markets"]

            if not markets_list:
                # No results; stop
                break

            aggregated.extend(markets_list)
            if len(aggregated) >= limit:
                aggregated = aggregated[:limit]
                break

            # Find next cursor
            cursor = data.get("next_cursor") or data.get("cursor") or data.get("next")
            if not cursor:
                break

        return aggregated

    def get_market_history_cached(self, market_id: str) -> List[Dict[str, Any]]:
        """Fetch stats history for a market.

        Strategy:
        1) Try current base URL's cached stats endpoint
        2) Try current base URL's non-cached stats endpoint
        3) If those fail (e.g., 404 on v2), resolve to elections v1:
           - If `market_id` looks like a ticker, resolve ID via
             `https://api.elections.kalshi.com/v1/markets_by_ticker/{ticker}`
           - Then GET `https://api.elections.kalshi.com/v1/markets/{id}/stats_history`
        """
        # 1) Try cached on current base
        try:
            data = self._get(f"cached/markets/{market_id}/stats_history")
            points = _extract_stats_points(data)
            if points:
                return points
        except Exception:
            pass

        # 2) Try non-cached on current base
        try:
            data = self._get(f"markets/{market_id}/stats_history")
            points = _extract_stats_points(data)
            if points:
                return points
        except Exception:
            pass

        # 3) Elections v1 fallback
        session = self.session

        def looks_like_uuid(s: str) -> bool:
            return len(s) >= 36 and s.count("-") >= 4

        market_uuid = market_id if looks_like_uuid(market_id) else None
        if market_uuid is None:
            # Resolve ticker -> id
            try:
                url = f"https://api.elections.kalshi.com/v1/markets_by_ticker/{market_id}"
                resp = session.get(url, timeout=self.timeout_s)
                if resp.status_code < 400:
                    j = resp.json()
                    market_uuid = j.get("market", {}).get("id")
            except Exception:
                market_uuid = None

        if market_uuid:
            for path in (
                f"https://api.elections.kalshi.com/v1/cached/markets/{market_uuid}/stats_history",
                f"https://api.elections.kalshi.com/v1/markets/{market_uuid}/stats_history",
            ):
                try:
                    r = session.get(path, timeout=self.timeout_s)
                    if r.status_code < 400:
                        # Some servers may return text/plain
                        try:
                            data = r.json()
                        except Exception:
                            # Try to load text into JSON (may still be JSON)
                            import json as _json  # local import to avoid overhead

                            data = _json.loads(r.text)
                        points = _extract_stats_points(data)
                        if points:
                            return points
                except Exception:
                    continue

        return []


def _extract_stats_points(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Attempt to standardize stats_history response to a list of dict points.

    Expected shapes include:
    - { "points": [ ... ] }
    - { "stats": [ ... ] }
    - [ ... ]
    """
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    for key in ("points", "stats", "history", "data"):
        val = data.get(key)
        if isinstance(val, list):
            return [p for p in val if isinstance(p, dict)]
    return []


def fetch_public_trades_elections_v1(session: requests.Session, market_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """Fetch recent public trades for a market from elections v1.

    Returns a list of dicts with at least create_date and price fields.
    """
    try:
        resp = session.get(
            "https://api.elections.kalshi.com/v1/trades",
            params={"market_id": market_id, "limit": min(limit, 1000)},
            timeout=15.0,
        )
        if resp.status_code >= 400:
            return []
        j = resp.json()
        trades = j.get("trades")
        return trades if isinstance(trades, list) else []
    except Exception:
        return []


def parse_iso8601(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        # Assume seconds since epoch if > 10^10 -> probably milliseconds
        value = float(ts)
        if value > 10_000_000_000:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(ts, str):
        try:
            # Common ISO formats
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None
    return None


def infer_price_field(point: Dict[str, Any]) -> Optional[str]:
    """Pick a reasonable field to treat as the price for candles.

    Preference order (first match wins): last_price, forecast, yes_price,
    last_trade_price, mid, close, price.
    """
    preferred_fields = (
        "last_price",
        "last_trade_price",
        "forecast",
        "yes_price",
        "mid",
        "close",
        "price",
    )
    for field in preferred_fields:
        if field in point and isinstance(point[field], (int, float)):
            return field
    # Fallback: try to locate a numeric field
    for k, v in point.items():
        if isinstance(v, (int, float)):
            return k
    return None


def build_candles(
    points: List[Dict[str, Any]],
    interval_seconds: int = 300,
) -> List[Dict[str, Any]]:
    """Aggregate time-series points into OHLC candles.

    - Expects each point to contain a timestamp (ts) in ISO8601 or epoch form.
    - Uses an inferred numeric price field when not specified.
    - Returns a list of candle dicts: {start, open, high, low, close, count}
    """
    if not points:
        return []

    # Normalize (ts, price)
    # Detect a price field from the first point that has one
    price_field: Optional[str] = None
    for p in points:
        price_field = infer_price_field(p)
        if price_field:
            break
    if not price_field:
        return []

    series: List[Tuple[datetime, float]] = []
    for p in points:
        ts = parse_iso8601(p.get("ts") or p.get("time") or p.get("timestamp"))
        val = p.get(price_field)
        if ts is None or not isinstance(val, (int, float)):
            continue
        series.append((ts, float(val)))

    if not series:
        return []

    # Sort by time
    series.sort(key=lambda x: x[0])

    def floor_bucket(t: datetime) -> datetime:
        epoch = int(t.timestamp())
        floored = epoch - (epoch % interval_seconds)
        return datetime.fromtimestamp(floored, tz=timezone.utc)

    buckets: Dict[datetime, List[float]] = {}
    for ts, price in series:
        b = floor_bucket(ts)
        buckets.setdefault(b, []).append(price)

    candles: List[Dict[str, Any]] = []
    for start in sorted(buckets.keys()):
        prices = buckets[start]
        open_p = prices[0]
        high_p = max(prices)
        low_p = min(prices)
        close_p = prices[-1]
        candles.append(
            {
                "start": start.isoformat(),
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "count": len(prices),
            }
        )

    return candles


def save_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def save_csv(path: Path, rows: List[Dict[str, Any]], field_order: Optional[List[str]] = None) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with path.open("w", newline="", encoding="utf-8") as f:
            f.write("")
        return

    if field_order is None:
        # Union of keys in insertion order
        keys: List[str] = []
        seen = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        field_order = keys

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=field_order)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in field_order})


def within_last_days(dt_str: Optional[str], days: int) -> bool:
    if not dt_str:
        return True
    try:
        dt = parse_iso8601(dt_str)
        if not dt:
            return True
        return dt >= datetime.now(timezone.utc) - timedelta(days=days)
    except Exception:
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and aggregate Kalshi NYC high temp market history (KXHIGHNY)")
    parser.add_argument("--series", default="KXHIGHNY", help="Series ticker to fetch (default: KXHIGHNY)")
    parser.add_argument("--base-url", default="https://trading-api.kalshi.com/v1", help="Kalshi API base URL")
    parser.add_argument("--outdir", default="data", help="Output directory")
    parser.add_argument("--days", type=int, default=120, help="Approx number of days back to keep markets (filter by market close/expiry if available)")
    parser.add_argument("--limit", type=int, default=2000, help="Max markets to fetch (safety bound)")
    parser.add_argument("--interval", default="5m", choices=["1m", "5m", "15m", "1h"], help="Candle interval")
    args = parser.parse_args()

    interval_map = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
    interval_seconds = interval_map[args.interval]

    out_dir = Path(args.outdir)
    raw_dir = out_dir / "raw"
    candles_dir = out_dir / "candles"

    # Optionally read API key file (not used unless you extend auth)
    key_id, _ = _read_api_key_file(Path("KALSHI_KEY.txt"))
    if key_id:
        print(f"Found Kalshi API key id: {key_id[:8]}… (not required for public cached endpoints)")

    client = KalshiClient(base_url=args.base_url)

    print(f"Listing markets for series {args.series}…")
    markets = client.list_markets_by_series(args.series, limit=args.limit)
    if not markets:
        print("No markets found. Exiting.")
        sys.exit(0)

    # Save market list for reference
    save_jsonl(out_dir / "markets.jsonl", markets)

    # Attempt to filter markets to roughly last N days using available timestamps
    def market_ts(m: Dict[str, Any]) -> Optional[str]:
        for k in ("close_time", "expiry_time", "expiration_time", "resolve_time", "settlement_time", "end_time"):
            v = m.get(k)
            if v:
                return str(v)
        return None

    filtered_markets: List[Dict[str, Any]] = [m for m in markets if within_last_days(market_ts(m), args.days)]
    if not filtered_markets:
        filtered_markets = markets

    print(f"Found {len(markets)} markets; using {len(filtered_markets)} within ~{args.days} days")

    combined_candles: List[Dict[str, Any]] = []
    failed_markets: List[Tuple[str, str]] = []

    for idx, m in enumerate(filtered_markets, start=1):
        market_id = m.get("id") or m.get("market_id") or m.get("ticker") or m.get("name")
        ticker = m.get("ticker") or m.get("market_ticker") or str(market_id)
        if not market_id:
            # Skip if we cannot identify an id/ticker for history endpoint
            continue

        print(f"[{idx}/{len(filtered_markets)}] Fetching history for {ticker}…")
        try:
            points = client.get_market_history_cached(str(market_id))
            if not points:
                # Try constructing from trades if stats_history is empty
                # Resolve ticker -> market UUID if needed
                market_uuid = None
                if len(str(market_id)) >= 36 and str(market_id).count("-") >= 4:
                    market_uuid = str(market_id)
                else:
                    try:
                        r = client.session.get(
                            f"https://api.elections.kalshi.com/v1/markets_by_ticker/{ticker}",
                            timeout=client.timeout_s,
                        )
                        if r.status_code < 400:
                            market_uuid = r.json().get("market", {}).get("id")
                    except Exception:
                        market_uuid = None

                if market_uuid:
                    trades = fetch_public_trades_elections_v1(client.session, market_uuid, limit=1000)
                    # Map to points compatible with candle builder
                    points = [
                        {"ts": t.get("create_date"), "last_price": float(t.get("price", 0))}
                        for t in trades
                        if t.get("create_date") is not None and isinstance(t.get("price"), (int, float))
                    ]
        except Exception as exc:  # noqa: BLE001
            failed_markets.append((str(market_id), f"history error: {exc}"))
            continue

        # Save raw points
        raw_path = raw_dir / f"{ticker}.jsonl"
        save_jsonl(raw_path, points)

        # Build candles and record
        candles = build_candles(points, interval_seconds=interval_seconds)
        for c in candles:
            c_with_meta = {"market_id": market_id, "ticker": ticker, **c}
            combined_candles.append(c_with_meta)

    # Save combined candles
    if combined_candles:
        csv_path = candles_dir / f"{args.series}_candles_{args.interval}.csv"
        save_csv(csv_path, combined_candles, field_order=["market_id", "ticker", "start", "open", "high", "low", "close", "count"])
        print(f"Wrote aggregated candles -> {csv_path}")
    else:
        print("No candles built (no data points found).")

    # Report failures (if any)
    if failed_markets:
        print(f"Failed {len(failed_markets)} markets:")
        for mid, reason in failed_markets[:10]:
            print(f"  - {mid}: {reason}")
        if len(failed_markets) > 10:
            print(f"  … and {len(failed_markets) - 10} more")


if __name__ == "__main__":
    main()


