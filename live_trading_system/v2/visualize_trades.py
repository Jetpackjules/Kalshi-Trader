import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import glob
from datetime import datetime

# --- Configuration ---
TRADES_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\v2\trades.csv"
LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
OUTPUT_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\v2\live_charts"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def generate_chart(date_str, trades, log_files):
    print(f"Generating chart for {date_str}...")
    
    # 1. Load Market Data for this Date
    # Find log file for this date
    # Format: market_data_KXHIGHNY-25DEC13.csv
    # Note: The log file contains data for multiple tickers.
    # We need to find the file that matches the date.
    
    # Actually, the log file name corresponds to the MARKET DATE.
    # But trades happen on a specific CALENDAR DATE.
    # We should load the log file that matches the trade's ticker suffix if possible,
    # OR just load the log file corresponding to the date we are visualizing.
    
    # Let's try to find the log file named market_data_KXHIGHNY-25{date_str}.csv
    # date_str format from trades is usually YYYY-MM-DD.
    # We need to convert to DEC13 format.
    
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        suffix = dt.strftime('%b%d').upper() # Dec13 -> DEC13
        log_filename = f"market_data_KXHIGHNY-25{suffix}.csv"
        log_path = os.path.join(LOG_DIR, log_filename)
        
        if not os.path.exists(log_path):
            print(f"  Warning: Log file {log_filename} not found. Trying to infer from trades...")
            # Fallback: Check tickers in trades
            tickers = set(t['ticker'] for t in trades)
            dfs = []
            for ticker in tickers:
                # Ticker format: KXHIGHNY-25DEC13-T43
                # Extract 25DEC13
                parts = ticker.split('-')
                if len(parts) >= 2:
                    mkt_date = parts[1] # 25DEC13
                    f = os.path.join(LOG_DIR, f"market_data_KXHIGHNY-{mkt_date}.csv")
                    if os.path.exists(f):
                        try:
                            df = pd.read_csv(f, on_bad_lines='skip')
                            df['timestamp'] = pd.to_datetime(df['timestamp'])
                            dfs.append(df)
                        except: pass
            
            if not dfs:
                print("  No market data found.")
                return
            
            full_df = pd.concat(dfs)
    
        else:
            full_df = pd.read_csv(log_path, on_bad_lines='skip')
            full_df['timestamp'] = pd.to_datetime(full_df['timestamp'])
            
    except Exception as e:
        print(f"  Error loading market data: {e}")
        return

    # Filter market data to the specific date (optional, but good for zoom)
    # Actually, let's just plot the whole file content to see context.
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
        subplot_titles=(f"Live Trading Activity - {date_str}", "Trade Log"),
        specs=[[{"type": "xy"}], [{"type": "table"}]]
    )
    
    # 1. Market Lines (Step Chart)
    for ticker in full_df['market_ticker'].unique():
        market_data = full_df[full_df['market_ticker'] == ticker]
        if market_data.empty: continue
        
        fig.add_trace(
            go.Scatter(
                x=market_data['timestamp'], 
                y=market_data['implied_no_ask'],
                mode='lines',
                name=ticker,
                line_shape='hv', # Step chart
                line=dict(width=1.5),
                opacity=0.7
            ),
            row=1, col=1
        )
        
    # 2. Trade Markers
    for t in trades:
        color = 'red' if 'NO' in t['action'] else 'green'
        symbol = 'circle'
        
        # Hover Text
        hover_text = (
            f"<b>{t['strategy']}</b><br>"
            f"{t['action']} {t['ticker']}<br>"
            f"Price: {t['price']}¢<br>"
            f"Qty: {t['qty']}<br>"
            f"Cost: ${t['cost']}<br>"
        )
        
        fig.add_trace(
            go.Scatter(
                x=[t['timestamp']],
                y=[t['price']],
                mode='markers',
                marker=dict(color=color, size=12, symbol=symbol, line=dict(width=2, color='black')),
                name=f"Trade: {t['ticker']}",
                text=hover_text,
                hoverinfo='text',
                showlegend=False
            ),
            row=1, col=1
        )

    # 3. Trade Table
    table_data = []
    for t in trades:
        table_data.append([
            t['timestamp'].strftime("%H:%M:%S"),
            t['strategy'],
            t['ticker'],
            t['action'],
            f"{t['price']}¢",
            t['qty'],
            f"${t['cost']}"
        ])
    
    if table_data:
        headers = ["Time", "Strategy", "Ticker", "Action", "Price", "Qty", "Cost"]
        fig.add_trace(
            go.Table(
                header=dict(values=headers, fill_color='paleturquoise', align='left'),
                cells=dict(values=list(zip(*table_data)), fill_color='lavender', align='left')
            ),
            row=2, col=1
        )

    fig.update_layout(
        height=1000,
        title_text=f"Live Trading Report: {date_str}",
        hovermode="closest"
    )
    fig.update_yaxes(title_text="Price / Prob", range=[0, 100], row=1, col=1)
    
    filename = os.path.join(OUTPUT_DIR, f"live_chart_{date_str}.html")
    fig.write_html(filename)
    print(f"  Chart saved to {filename}")

def main():
    print("=== Visualizing Live Trades ===")
    
    if not os.path.exists(TRADES_FILE):
        print("No trades.csv found.")
        return
        
    # Load Trades
    df = pd.read_csv(TRADES_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Group by Date
    # We want to group by the CALENDAR DATE of the trade
    df['date_str'] = df['timestamp'].dt.strftime('%Y-%m-%d')
    
    grouped = df.groupby('date_str')
    
    for date_str, group in grouped:
        trades = group.to_dict('records')
        generate_chart(date_str, trades, LOG_DIR)

if __name__ == "__main__":
    main()
