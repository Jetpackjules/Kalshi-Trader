import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from collections import defaultdict

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add server_mirror to path
sys.path.insert(0, os.path.join(os.getcwd(), "server_mirror"))
from backtesting.engine import parse_market_date_from_ticker

def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    raw = value.replace("T", " ").replace("_", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H%M%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None

def get_market_end_time(ticker: str) -> datetime | None:
    d = parse_market_date_from_ticker(ticker)
    if d is None:
        return None
    # Settlement is 5 AM UTC next day (matching UnifiedEngine)
    return (d + timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)

def main():
    parser = argparse.ArgumentParser(description="Generate Variant-Style Graph for Unified Engine")
    parser.add_argument("--out-dir", type=str, action="append", help="Backtest output directory. Repeatable.")
    parser.add_argument("--label", type=str, action="append", help="Label for the strategy. Repeatable.")
    parser.add_argument("--manifest", type=str, help="Path to JSON manifest containing out_dirs and labels")
    parser.add_argument("--snapshot", type=str, required=True, help="Path to starting snapshot")
    parser.add_argument("--out", type=str, default="backtest_charts/unified_variant_comparison.html", help="Output HTML path")
    args = parser.parse_args()

    out_dirs = args.out_dir or []
    labels = args.label or []

    if args.manifest:
        with open(args.manifest, "r") as f:
            manifest = json.load(f)
            for item in manifest:
                out_dirs.append(item["out_dir"])
                labels.append(item["label"])

    if not out_dirs or not labels:
        print("Error: At least one --out-dir and --label pair (or a --manifest) is required.")
        return
    
    if len(out_dirs) != len(labels):
        print("Error: Number of --out-dir and --label must match.")
        return

    # Load Snapshot
    with open(args.snapshot, "r") as f:
        snapshot = json.load(f)
    
    initial_cash = float(snapshot.get("balance") or snapshot.get("cash") or 0.0)
    initial_positions = snapshot.get("positions", {})
    start_dt = _parse_timestamp(snapshot.get("timestamp") or snapshot.get("last_update"))

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Equity (MTM) by Strategy", "Daily Return (%)"),
    )

    all_equities = []

    total_variants = len(out_dirs)
    print(f"Processing {total_variants} variants...")
    
    for i, (out_dir_str, label) in enumerate(zip(out_dirs, labels), 1):
        if i % 10 == 0:
            print(f"[{i}/{total_variants}] Processing {label}...", flush=True)
        out_dir = Path(out_dir_str)
        equity_history_path = out_dir / "equity_history.csv"
        trades_path = out_dir / "unified_trades.csv"
        
        if not trades_path.exists() and not equity_history_path.exists():
            print(f"Warning: {trades_path} not found. Skipping {label}.")
            continue

        daily_history = []
        if equity_history_path.exists():
            # Resample per-tick data to per-day
            daily_history_map = {} # {date_str: equity}
            with open(equity_history_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    dt = _parse_timestamp(row.get("date"))
                    if not dt:
                        continue
                    
                    # Use YYYY-MM-DD for sortable key
                    date_key = dt.date().isoformat()
                    # Keep the last entry for each day
                    daily_history_map[date_key] = float(row["equity"])
            
            # Convert map back to sorted list of displayable points
            for d_key in sorted(daily_history_map.keys()):
                dt = datetime.fromisoformat(d_key)
                display_date = dt.strftime("%y%b%d").upper()
                daily_history.append(
                    {
                        "date": display_date,
                        "equity": daily_history_map[d_key],
                    }
                )
        else:
            # Reconstruct from trades if equity history is missing
            trades = []
            with open(trades_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["time"] = _parse_timestamp(row["time"])
                    row["price"] = float(row["price"])
                    row["qty"] = int(row["qty"])
                    row["cost"] = float(row.get("cost") or (row["price"] * row["qty"] / 100.0))
                    trades.append(row)
            
            trades.sort(key=lambda x: x["time"])

            all_times = [t["time"] for t in trades]
            if start_dt:
                all_times.append(start_dt)
            
            if not all_times:
                continue

            min_date = min(all_times).date()
            max_date = max(all_times).date()
            
            current_cash = initial_cash
            current_positions = defaultdict(lambda: {"yes": 0, "no": 0})
            for ticker, pos in initial_positions.items():
                current_positions[ticker]["yes"] = int(pos.get("yes", 0))
                current_positions[ticker]["no"] = int(pos.get("no", 0))

            trade_idx = 0
            settled_tickers = set()
            last_price_cache = {}

            def get_last_price(ticker):
                if ticker in last_price_cache:
                    return last_price_cache[ticker]
                parts = ticker.split('-')
                if len(parts) < 2: return 50.0
                ticker_base = f"{parts[0]}-{parts[1]}"
                market_file = Path(f"vm_logs/market_logs/market_data_{ticker_base}.csv")
                last_price = 50.0
                if market_file.exists():
                    try:
                        df_m = pd.read_csv(market_file, usecols=['market_ticker', 'best_yes_bid', 'implied_yes_ask'])
                        ticker_data = df_m[df_m['market_ticker'] == ticker]
                        if not ticker_data.empty:
                            last_row = ticker_data.iloc[-1]
                            ya = last_row.get('implied_yes_ask')
                            yb = last_row.get('best_yes_bid')
                            if pd.notna(ya) and pd.notna(yb):
                                last_price = (float(ya) + float(yb)) / 2.0
                            elif pd.notna(ya): last_price = float(ya)
                            elif pd.notna(yb): last_price = float(yb)
                    except: pass
                last_price_cache[ticker] = last_price
                return last_price

            curr_d = min_date
            while curr_d <= max_date:
                day_end = datetime.combine(curr_d, dt_time(23, 59, 59, 999999))
                while trade_idx < len(trades) and trades[trade_idx]["time"] <= day_end:
                    t = trades[trade_idx]
                    ticker, action, qty, cost = t["ticker"], t["action"], t["qty"], t["cost"]
                    if action == "BUY_YES": current_positions[ticker]["yes"] += qty; current_cash -= cost
                    elif action == "BUY_NO": current_positions[ticker]["no"] += qty; current_cash -= cost
                    elif action == "SELL_YES": current_positions[ticker]["yes"] -= qty; current_cash += cost
                    elif action == "SELL_NO": current_positions[ticker]["no"] -= qty; current_cash += cost
                    trade_idx += 1

                for ticker in list(current_positions.keys()):
                    if ticker in settled_tickers: continue
                    settle_time = get_market_end_time(ticker)
                    if settle_time and settle_time <= day_end:
                        last_price = get_last_price(ticker)
                        yes_qty, no_qty = current_positions[ticker]["yes"], current_positions[ticker]["no"]
                        settle_val = 100.0 if last_price >= 50.0 else 0.0
                        payout = (yes_qty * (settle_val / 100.0)) + (no_qty * ((100.0 - settle_val) / 100.0))
                        current_cash += payout
                        del current_positions[ticker]
                        settled_tickers.add(ticker)

                mtm_val = 0.0
                for ticker, pos in current_positions.items():
                    last_price = get_last_price(ticker)
                    mtm_val += (pos["yes"] * (last_price / 100.0)) + (pos["no"] * ((100.0 - last_price) / 100.0))
                
                daily_history.append({"date": curr_d.strftime("%y%b%d").upper(), "equity": current_cash + mtm_val})
                curr_d += timedelta(days=1)

        if not daily_history:
            continue

        dates = [h["date"] for h in daily_history]
        equities = [h["equity"] for h in daily_history]
        if equities:
            print(f"DEBUG: {label} final equity: {equities[-1]}")
        all_equities.append(equities)

        # Plotting
        line_style = dict()
        if "all-day" in label.lower() or "24/7" in label.lower():
            line_style = dict(dash='dot')

        fig.add_trace(
            go.Scatter(x=dates, y=equities, mode="lines+markers", name=label, line=line_style),
            row=1, col=1
        )

        # Daily ROI Bars
        if len(out_dirs) == 1 or out_dir_str == out_dirs[0]:
            daily_rets = []
            prev = None
            for e in equities:
                if prev is None or prev == 0: daily_rets.append(0.0)
                else: daily_rets.append((e - prev) / prev * 100.0)
                prev = e
            fig.add_trace(
                go.Bar(x=dates, y=daily_rets, name=f"{label} daily %", opacity=0.35, showlegend=False),
                row=2, col=1
            )

    if not all_equities:
        print("Error: No data found to plot!")
        return

    fig.update_layout(
        title=f"Unified Variant Comparison",
        hovermode="x unified",
        height=900,
    )
    fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
    fig.update_yaxes(title_text="Daily Return (%)", row=2, col=1)

    out_dir_path = os.path.dirname(args.out)
    if out_dir_path:
        os.makedirs(out_dir_path, exist_ok=True)
    
    fig.write_html(args.out)
    print(f"Wrote variant comparison chart: {args.out}")

if __name__ == "__main__":
    main()
