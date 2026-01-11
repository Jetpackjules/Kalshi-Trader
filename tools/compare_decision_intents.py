import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_decisions(path: str, include_keep: bool) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            decision_type = (row.get("decision_type") or "").strip().lower()
            if not include_keep and decision_type != "desired":
                continue
            tick_time = _parse_time(row.get("tick_time") or "")
            if tick_time is None:
                continue
            row["_tick_dt"] = tick_time
            tick_seq_raw = row.get("tick_seq")
            row["_tick_seq"] = int(tick_seq_raw) if tick_seq_raw not in (None, "") else None
            row["_tick_source"] = row.get("tick_source") or ""
            tick_row_raw = row.get("tick_row")
            row["_tick_row"] = int(tick_row_raw) if tick_row_raw not in (None, "") else None
            row["_ticker"] = row.get("ticker") or ""
            row["_action"] = row.get("action") or ""
            row["_price"] = float(row["price"]) if row.get("price") not in (None, "") else None
            row["_qty"] = int(row["qty"]) if row.get("qty") not in (None, "") else None
            rows.append(row)
    rows.sort(key=lambda r: r["_tick_dt"])
    return rows


def _build_index(rows: list[dict], match_on_seq: bool) -> dict[tuple, list[dict]]:
    index = defaultdict(list)
    for row in rows:
        if match_on_seq:
            key = (row["_tick_seq"], row["_ticker"], row["_action"], row["_price"], row["_qty"])
        else:
            key = (row["_ticker"], row["_action"], row["_price"], row["_qty"])
        index[key].append(row)
    for key in index:
        index[key].sort(key=lambda r: r["_tick_dt"])
    return index


def _find_best_match(candidates: list[dict], target_time: datetime, window: timedelta) -> tuple[int | None, float | None]:
    best_idx = None
    best_delta = None
    for idx, row in enumerate(candidates):
        delta = abs(row["_tick_dt"] - target_time)
        if delta <= window and (best_delta is None or delta < best_delta):
            best_idx = idx
            best_delta = delta.total_seconds()
    return best_idx, best_delta


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare decision intent logs.")
    parser.add_argument("--backtest", required=True, help="Backtest decision_intents.csv path")
    parser.add_argument("--live", required=True, help="Live decision_intents.csv path")
    parser.add_argument("--time-window-s", type=float, default=1.0, help="Match window in seconds")
    parser.add_argument("--include-keep", action="store_true", help="Include keep/empty decisions")
    parser.add_argument("--match-on-seq", action="store_true", help="Require matching tick_seq values")
    args = parser.parse_args()

    backtest_rows = _load_decisions(args.backtest, args.include_keep)
    live_rows = _load_decisions(args.live, args.include_keep)
    window = timedelta(seconds=float(args.time_window_s))

    live_index = _build_index(live_rows, args.match_on_seq)
    live_by_ticker_action = defaultdict(list)
    for row in live_rows:
        key = (row["_ticker"], row["_action"])
        live_by_ticker_action[key].append(row)
    for key in live_by_ticker_action:
        live_by_ticker_action[key].sort(key=lambda r: r["_tick_dt"])

    matched = 0
    first_mismatch = None

    for row in backtest_rows:
        if args.match_on_seq and row["_tick_seq"] is None:
            first_mismatch = (row, None, None, None)
            break
        if args.match_on_seq:
            key = (row["_tick_seq"], row["_ticker"], row["_action"], row["_price"], row["_qty"])
        else:
            key = (row["_ticker"], row["_action"], row["_price"], row["_qty"])
        candidates = live_index.get(key, [])
        idx, delta_s = _find_best_match(candidates, row["_tick_dt"], window)
        if idx is not None:
            candidates.pop(idx)
            matched += 1
            continue

        # Fallback: closest same ticker+action for context
        alt_candidates = live_by_ticker_action.get((row["_ticker"], row["_action"]), [])
        alt_idx, alt_delta_s = _find_best_match(alt_candidates, row["_tick_dt"], window)
        alt_row = alt_candidates[alt_idx] if alt_idx is not None else None
        first_mismatch = (row, delta_s, alt_row, alt_delta_s)
        break

    total = len(backtest_rows)
    if first_mismatch is None:
        print(f"All {matched}/{total} decision intents matched within {args.time_window_s}s.")
        return 0

    row, _, alt_row, alt_delta_s = first_mismatch
    print("FIRST MISMATCH:")
    print(
        f"  Backtest: tick_time={row['_tick_dt'].isoformat()} tick_seq={row.get('_tick_seq')} "
        f"ticker={row['_ticker']} action={row['_action']} price={row['_price']} qty={row['_qty']}"
    )
    if alt_row:
        print(
            "  Closest same ticker+action: "
            f"tick_time={alt_row['_tick_dt'].isoformat()} tick_seq={alt_row.get('_tick_seq')} "
            f"price={alt_row['_price']} qty={alt_row['_qty']} delta_s={alt_delta_s:.3f}"
        )
    else:
        print("  Closest same ticker+action: NONE")
    print(f"Matched {matched}/{total} within {args.time_window_s}s before mismatch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
