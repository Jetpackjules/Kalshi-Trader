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

def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.replace("T", " ").replace("_", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H%M%S"):
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
    parser.add_argument("--snapshot", type=str, required=True, help="Path to starting snapshot")
    parser.add_argument("--out", type=str, default="backtest_charts/unified_variant_comparison.html", help="Output HTML path")
    args = parser.parse_args()

    if not args.out_dir or not args.label:
        print("Error: At least one --out-dir and --label pair is required.")
        return
    
    if len(args.out_dir) != len(args.label):
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

    for out_dir_str, label in zip(args.out_dir, args.label):
        out_dir = Path(out_dir_str)
        trades_path = out_dir / "unified_trades.csv"
        if not trades_path.exists():
            print(f"Warning: {trades_path} not found. Skipping {label}.")
            continue

        # Load Trades
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

        # Reconstruct Daily Equity
        all_times = [t["time"] for t in trades]
        if start_dt:
            all_times.append(start_dt)
        
        if not all_times:
            continue

        min_date = min(all_times).date()
        max_date = max(all_times).date()
        
        daily_history = []
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

        dates = [h["date"] for h in daily_history]
        equities = [h["equity"] for h in daily_history]
        all_equities.append(equities)

        # Plotting
        line_style = dict()
        if "all-day" in label.lower() or "24/7" in label.lower():
            line_style = dict(dash='dot')

        fig.add_trace(
            go.Scatter(x=dates, y=equities, mode="lines+markers", name=label, line=line_style),
            row=1, col=1
        )

        # Only plot daily returns for the first strategy to avoid clutter, 
        # or if there's only one strategy.
        if len(args.out_dir) == 1 or out_dir_str == args.out_dir[0]:
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

    fig.update_layout(
        title=f"Unified Variant Comparison",
        hovermode="x unified",
        height=900,
    )
    fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
    fig.update_yaxes(title_text="Daily Return (%)", row=2, col=1)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.write_html(args.out)
    print(f"Wrote variant comparison chart: {args.out}")
    if all_equities:
        print(f"Final Reconstructed Equities:")
        for label, eqs in zip(args.label, all_equities):
            print(f"  {label}: ${eqs[-1]:.2f}")

if __name__ == "__main__":
    main()
