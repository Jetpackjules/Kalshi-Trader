import json
import os
import re
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go

# Paths
TRADER_LOG = os.path.join("server_mirror", "output.log")
FILLS_FILE = os.path.join("vm_logs", "todays_fills.json")
OUTPUT_CHART = os.path.join("backtest_charts", "real_portfolio_performance_today.html")

def generate_chart():
    print("Parsing fills from Kalshi API output...")
    if not os.path.exists(FILLS_FILE):
        print(f"Error: {FILLS_FILE} not found. Run get_todays_trades.py first.")
        return

    with open(FILLS_FILE, "r", encoding="utf-16") as f:
        fills_blob = json.load(f)

    fills = fills_blob.get("fills", [])
    if not fills:
        print("No fills found in todays_fills.json.")
    
    print("Parsing trader log for equity curve...")
    equity_history = []

    # Try to anchor the log date from the snapshot filename in output.log
    anchor_date = None
    if os.path.exists(TRADER_LOG):
        with open(TRADER_LOG, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                snap_match = re.search(r"snapshot_(\d{4}-\d{2}-\d{2})", line)
                if snap_match:
                    anchor_date = datetime.strptime(snap_match.group(1), "%Y-%m-%d").date()
    if anchor_date is None:
        # Fallback to local date from fills file
        today_str = fills_blob.get("date_local")
        anchor_date = datetime.strptime(today_str, "%Y-%m-%d").date() if today_str else datetime.now().date()

    current_date = anchor_date
    last_time = None
    
    if os.path.exists(TRADER_LOG):
        with open(TRADER_LOG, 'r', errors='ignore') as f:
            for line in f:
                # Look for TICK lines to update current_date
                tick_match = re.search(r'TICK \S+ (\d{4}-\d{2}-\d{2})', line)
                if tick_match:
                    new_date = datetime.strptime(tick_match.group(1), "%Y-%m-%d").date()
                    if current_date != new_date:
                        print(f"Date changed (TICK) to: {new_date}")
                        current_date = new_date

                # Look for "TRY_ORDER" or other lines with timestamps if any
                # Actually, trades.csv is better.
                
                # Look for "--- Status @ HH:MM:SS ---"
                time_match = re.search(r'--- Status @ (\d{2}:\d{2}:\d{2}) ---', line)
                if time_match:
                    time_str = time_match.group(1)
                    t = datetime.strptime(time_str, "%H:%M:%S").time()
                    
                    # Detect date rollover
                    if last_time and t < last_time:
                        # Only increment if it's a significant jump backwards (e.g. > 1h)
                        # to avoid small jitter issues
                        if (datetime.combine(datetime.min, last_time) - datetime.combine(datetime.min, t)).total_seconds() > 3600:
                            current_date += timedelta(days=1)
                            print(f"Date rolled over to: {current_date}")
                    last_time = t
                    
                    # Read next line for Equity
                    try:
                        next_line = next(f)
                        equity_match = re.search(r'Equity: \$([\d\.]+)', next_line)
                        if equity_match:
                            equity = float(equity_match.group(1))
                            if current_date:
                                dt = datetime.combine(current_date, t)
                                equity_history.append({'timestamp': dt, 'equity': equity})
                    except StopIteration:
                        break
    
    print(f"Found {len(equity_history)} equity entries in log.")

    df_equity = pd.DataFrame(equity_history)
    
    # Filter to today's date (local)
    today_str = fills_blob.get("date_local")
    if today_str:
        today_date = datetime.strptime(today_str, "%Y-%m-%d").date()
        df_equity = df_equity[df_equity["timestamp"].dt.date == today_date]
    
    if df_equity.empty:
        print("No equity data found for today.")
        return

    # Downsample to hourly or just keep all if not too many
    # Let's keep all for now, but maybe take the last one per minute to smooth
    df_equity = df_equity.set_index('timestamp').resample('1min').last().dropna().reset_index()

    print(f"Generating chart with {len(df_equity)} points...")
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_equity['timestamp'],
        y=df_equity['equity'],
        mode='lines',
        name='Real Portfolio Equity',
        line=dict(color='green', width=3),
        fill='tozeroy',
        fillcolor='rgba(0, 255, 0, 0.1)'
    ))
    
    # Add fill markers
    for fill in fills:
        ts = fill.get("ts")
        if ts is None:
            continue
        tstamp = datetime.fromtimestamp(ts)
        if today_str and tstamp.date() != today_date:
            continue
        side = fill.get("side", "").upper()
        action = fill.get("action", "").upper()
        color = "blue" if side == "YES" else "red"
        price = fill.get("yes_price") if side == "YES" else fill.get("no_price")
        qty = fill.get("count")
        ticker = fill.get("market_ticker") or fill.get("ticker")

        # Snap marker to nearest equity point for a clean overlay
        nearest_idx = (df_equity["timestamp"] - tstamp).abs().argsort()[:1]
        if len(nearest_idx) == 0:
            continue
        y_val = df_equity.iloc[nearest_idx]["equity"].values[0]

        fig.add_trace(go.Scatter(
            x=[tstamp],
            y=[y_val],
            mode="markers",
            marker=dict(color=color, size=8, symbol="diamond"),
            name=f"{action}_{side} {ticker}",
            hovertext=f"{action} {side} {ticker}<br>Price: {price}c<br>Qty: {qty}",
            showlegend=False,
        ))

    fig.update_layout(
        title="Real Kalshi Portfolio Performance (Today)",
        xaxis_title="Date/Time",
        yaxis_title="Portfolio Value ($)",
        hovermode="x unified",
        template="plotly_dark",
        height=800,
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        )
    )
    
    # Add baseline (Initial Capital on Dec 24)
    initial_equity = df_equity.iloc[0]['equity']
    fig.add_hline(y=initial_equity, line_dash="dash", line_color="gray", annotation_text=f"Start: ${initial_equity:.2f}")
    
    os.makedirs(os.path.dirname(OUTPUT_CHART), exist_ok=True)
    fig.write_html(OUTPUT_CHART)
    print(f"Chart generated: {OUTPUT_CHART}")

if __name__ == "__main__":
    generate_chart()
