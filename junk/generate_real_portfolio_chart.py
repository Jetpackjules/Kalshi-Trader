import pandas as pd
import plotly.graph_objects as go
import os
import re
from datetime import datetime, timedelta

# Paths
VM_LOGS_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs"
TRADES_FILE = os.path.join(VM_LOGS_DIR, "trades.csv")
TRADER_LOG = os.path.join(VM_LOGS_DIR, "live_trader_v4.log")
OUTPUT_CHART = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\backtest_charts\real_portfolio_performance.html"

def generate_chart():
    print("Parsing trades...")
    if not os.path.exists(TRADES_FILE):
        print(f"Error: {TRADES_FILE} not found.")
        return

    df_trades = pd.read_csv(TRADES_FILE)
    df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
    
    # Filter since Dec 24
    df_trades = df_trades[df_trades['timestamp'] >= '2025-12-24']
    
    if df_trades.empty:
        print("No trades found since Dec 24.")
        # We might still have equity data in the log even without trades.
    
    print("Parsing trader log for equity curve...")
    equity_history = []
    
    # Load trades to help anchor dates
    df_trades = pd.read_csv(TRADES_FILE)
    df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
    trade_dates = df_trades.set_index('timestamp').index.to_series().dt.date.to_dict()
    
    current_date = datetime(2025, 12, 23).date() # Log starts on Dec 23
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
    
    # Filter since Dec 24
    df_equity = df_equity[df_equity['timestamp'] >= '2025-12-24']
    
    if df_equity.empty:
        print("No equity data found since Dec 24.")
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
    
    # Add trade markers
    for _, trade in df_trades.iterrows():
        color = 'blue' if 'BUY_YES' in trade['action'] else 'red'
        fig.add_trace(go.Scatter(
            x=[trade['timestamp']],
            y=[df_equity.iloc[(df_equity['timestamp']-trade['timestamp']).abs().argsort()[:1]]['equity'].values[0]],
            mode='markers',
            marker=dict(color=color, size=8, symbol='diamond'),
            name=f"{trade['action']} {trade['ticker']}",
            hovertext=f"{trade['action']} {trade['ticker']}<br>Price: {trade['price']}c<br>Qty: {trade['qty']}<br>Cost: ${trade['cost']:.2f}",
            showlegend=False
        ))

    fig.update_layout(
        title="Real Kalshi Portfolio Performance (Since Dec 24)",
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
