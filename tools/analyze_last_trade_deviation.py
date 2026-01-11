import argparse
import os
from statistics import mean


def _parse_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _load_rows(path):
    with open(path, "r", encoding="utf-8") as f:
        header = f.readline().strip("\n")
        if not header:
            return [], {}
        columns = header.split(",")
        idx = {name: i for i, name in enumerate(columns)}

        rows = []
        for line in f:
            line = line.strip("\n")
            if not line:
                continue
            cols = line.split(",")
            last_trade = None
            if "last_trade_price" in idx:
                lt_idx = idx["last_trade_price"]
                if lt_idx < len(cols):
                    last_trade = cols[lt_idx]
            elif len(cols) > len(columns):
                last_trade = cols[-1]

            row = {
                "best_yes_bid": cols[idx["best_yes_bid"]] if "best_yes_bid" in idx and idx["best_yes_bid"] < len(cols) else None,
                "best_no_bid": cols[idx["best_no_bid"]] if "best_no_bid" in idx and idx["best_no_bid"] < len(cols) else None,
                "implied_no_ask": cols[idx["implied_no_ask"]] if "implied_no_ask" in idx and idx["implied_no_ask"] < len(cols) else None,
                "implied_yes_ask": cols[idx["implied_yes_ask"]] if "implied_yes_ask" in idx and idx["implied_yes_ask"] < len(cols) else None,
                "last_trade_price": last_trade,
            }
            rows.append(row)
    return rows, idx


def _compute_deviations(rows):
    metrics = {
        "best_yes_bid": [],
        "best_no_bid": [],
        "implied_no_ask_as_yes": [],
        "implied_yes_ask": [],
        "mid_implied": [],
    }

    total = 0
    for row in rows:
        lp = _parse_float(row.get("last_trade_price"))
        if lp is None:
            continue
        total += 1
        yb = _parse_float(row.get("best_yes_bid"))
        nb = _parse_float(row.get("best_no_bid"))
        na = _parse_float(row.get("implied_no_ask"))
        ya = _parse_float(row.get("implied_yes_ask"))

        if yb is not None:
            metrics["best_yes_bid"].append(abs(yb - lp))
        if nb is not None:
            metrics["best_no_bid"].append(abs(nb - lp))
        if na is not None:
            metrics["implied_no_ask_as_yes"].append(abs((100.0 - na) - lp))
        if ya is not None:
            metrics["implied_yes_ask"].append(abs(ya - lp))
        if ya is not None and na is not None:
            mid = (ya + (100.0 - na)) / 2.0
            metrics["mid_implied"].append(abs(mid - lp))

    return total, metrics


def main():
    parser = argparse.ArgumentParser(
        description="Analyze deviation between last_trade_price and quote-derived proxies."
    )
    parser.add_argument("paths", nargs="+", help="CSV paths to analyze")
    args = parser.parse_args()

    for path in args.paths:
        if not os.path.exists(path):
            print(f"{path}: missing")
            continue
        rows, idx = _load_rows(path)
        total, metrics = _compute_deviations(rows)
        print(f"{os.path.basename(path)} rows_with_last_trade={total}")
        if total == 0:
            continue
        for key, vals in metrics.items():
            if not vals:
                continue
            print(f"  {key}: avg_abs_err={mean(vals):.3f}")


if __name__ == "__main__":
    main()
