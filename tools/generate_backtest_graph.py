import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from collections import defaultdict

import pandas as pd
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

def main():
    parser = argparse.ArgumentParser(description="Generate Granular Daily Backtest Charts")
    parser.add_argument("--out-dir", type=str, required=True, help="Backtest output directory.")
    parser.add_argument("--initial-cash", type=float, default=100.0, help="Initial cash (default: 100.0)")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD). If omitted, uses first trade.")
    parser.add_argument("--out", type=str, default="backtest_charts/granular_daily.html", help="Output HTML path")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    trades_path = out_dir / "unified_trades.csv"
    
    if not trades_path.exists():
        print(f"Error: {trades_path} not found.")
        return

    # Initialize from Args (No Snapshot)
    initial_cash = args.initial_cash
    initial_positions = {}
    start_dt = _parse_timestamp(args.start_date) if args.start_date else None

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
    
    # Filter by start date if provided
    if start_dt:
        trades = [t for t in trades if t["time"] >= start_dt]

    if not trades:
        print("No trades found.")
        return

    all_times = [t["time"] for t in trades]
    if start_dt:
        all_times.append(start_dt)
    
    min_date = min(all_times).date()
    max_date = max(all_times).date()
    
    # Process Day by Day
    current_cash = initial_cash
    current_positions = defaultdict(lambda: {"yes": 0, "no": 0})
    for ticker, pos in initial_positions.items():
        current_positions[ticker]["yes"] = int(pos.get("yes", 0))
        current_positions[ticker]["no"] = int(pos.get("no", 0))

    trade_idx = 0
    curr_d = min_date
    
    figures = []

    while curr_d <= max_date:
        day_date = curr_d
        day_start = datetime.combine(curr_d, dt_time(0, 0, 0))
        day_end = datetime.combine(curr_d, dt_time(23, 59, 59, 999999))
        
        # Collect day's data points
        equity_curve = [] # (time, equity)
        inventory_curve = [] # (time, net_position)
        
        day_trades = []
        while trade_idx < len(trades) and trades[trade_idx]["time"] <= day_end:
            t_row = trades[trade_idx]
            trade_idx += 1
            day_trades.append(t_row)
            
            # Apply Trade
            ticker, action, qty, cost = t_row["ticker"], t_row["action"], t_row["qty"], t_row["cost"]
            if action == "BUY_YES": current_positions[ticker]["yes"] += qty; current_cash -= cost
            elif action == "BUY_NO": current_positions[ticker]["no"] += qty; current_cash -= cost
            elif action == "SELL_YES": current_positions[ticker]["yes"] -= qty; current_cash += cost
            elif action == "SELL_NO": current_positions[ticker]["no"] -= qty; current_cash += cost
            
            # Estimate Equity (Cash + Cost Basis for speed, or just Cash)
            # For granular chart, let's just plot CASH for simplicity or approx equity
            # Calculating real equity requires market data lookup which is heavy
            equity_curve.append((t_row["time"], current_cash))
            
            # Track Net Inventory of the active ticker (simplified)
            net = current_positions[ticker]["yes"] - current_positions[ticker]["no"]
            inventory_curve.append((t_row["time"], net, ticker))

        if not day_trades:
            curr_d += timedelta(days=1)
            continue

        # Plot Day
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, 
                            subplot_titles=(f"Cash & Trades ({day_date})", "Inventory"))
        
        # Cash Line
        if equity_curve:
            times, vals = zip(*equity_curve)
            fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='Cash', line=dict(color='green')), row=1, col=1)
        
        # Trade Markers
        buys_x, buys_y = [], []
        sells_x, sells_y = [], []
        for t in day_trades:
            if "BUY" in t["action"]:
                buys_x.append(t["time"])
                buys_y.append(t["price"]) # Using Price for Y axis on separate chart? No, overlay on Cash is confusing.
                # Let's put markers on the Cash line? Or just a separate Price chart?
                # User asked for "Granular".
                pass 

        # Inventory Line
        if inventory_curve:
            times, vals, tickers = zip(*inventory_curve)
            # Filter for most active ticker?
            fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='Net Inv', line=dict(color='blue')), row=2, col=1)

        fig.update_layout(height=600, title_text=f"Backtest Granularity: {day_date}", showlegend=True)
        figures.append(fig.to_html(full_html=False, include_plotlyjs='cdn'))
        
        curr_d += timedelta(days=1)

    # Combine into one HTML
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("<html><head><title>Granular Backtest</title></head><body>")
        for h in figures:
            f.write(h)
            f.write("<hr>")
        f.write("</body></html>")
    
    print(f"Generated granular charts at {args.out}")

if __name__ == "__main__":
    main()
