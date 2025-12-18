import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import glob

# Configuration
CHARTS_DIR = "backtest_charts"
DATE_STR = "25DEC17"
MARKET_FILE_PATTERN = f"market_data_*{DATE_STR}*.csv"
LOG_DIR = r"C:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"

def load_market_data():
    files = glob.glob(os.path.join(LOG_DIR, MARKET_FILE_PATTERN))
    if not files:
        print("No market data found for Dec 17")
        return pd.DataFrame()
    
    # Use the largest file (most complete)
    files.sort(key=os.path.getsize, reverse=True)
    df = pd.read_csv(files[0], on_bad_lines='skip')
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
    return df

def load_trades(filename, label):
    try:
        df = pd.read_csv(filename)
        df['Run'] = label
        # Filter for Safe Baseline only
        df = df[df['strategy'].str.contains("Safe Baseline", case=False, regex=False)]
        return df
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return pd.DataFrame()

def generate_chart():
    print("Loading Data...")
    market_df = load_market_data()
    
    trades_og = load_trades('trades_og.csv', 'OG Fast (183% ROI)')
    trades_filtered = load_trades('trades_1s.csv', 'Filtered (1s)')
    trades_unfiltered = load_trades('trades_unfiltered.csv', 'Unfiltered (Ghost Chaser)')
    
    all_trades = [trades_og, trades_filtered, trades_unfiltered]
    
    print("Generating Chart...")
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
        subplot_titles=(f"Grand Comparison: Dec 17 ({DATE_STR})", "Trade Details"),
        specs=[[{"type": "xy"}], [{"type": "table"}]]
    )
    
    # 1. Market Lines (Step Chart)
    # Plot the most active ticker for clarity, or all of them?
    # Let's plot the tickers that were actually traded.
    traded_tickers = set()
    for df in all_trades:
        if not df.empty:
            traded_tickers.update(df['ticker'].unique())
            
    if not traded_tickers:
        # Fallback: Plot top 3 tickers by volume/activity
        traded_tickers = market_df['market_ticker'].unique()[:3]
        
    for ticker in traded_tickers:
        m_data = market_df[market_df['market_ticker'] == ticker]
        if m_data.empty: continue
        
        fig.add_trace(
            go.Scatter(
                x=m_data['timestamp'], 
                y=m_data['implied_no_ask'],
                mode='lines',
                name=f"Market: {ticker}",
                line_shape='hv',
                line=dict(width=1),
                opacity=0.5
            ),
            row=1, col=1
        )

    # 2. Trade Markers
    # Define styles for each run
    styles = {
        'OG Fast (183% ROI)': {'color': 'green', 'symbol': 'star', 'size': 15},
        'Filtered (1s)': {'color': 'blue', 'symbol': 'circle', 'size': 12},
        'Unfiltered (Ghost Chaser)': {'color': 'red', 'symbol': 'x', 'size': 12}
    }
    
    for df in all_trades:
        if df.empty: continue
        run_name = df['Run'].iloc[0]
        style = styles.get(run_name, {'color': 'gray', 'symbol': 'circle', 'size': 10})
        
        # Tooltip
        hover_text = df.apply(lambda row: (
            f"<b>{run_name}</b><br>"
            f"{row['action']} {row['ticker']}<br>"
            f"Price: {row['price']:.0f}¢<br>"
            f"Time: {row['time']}"
        ), axis=1)
        
        fig.add_trace(
            go.Scatter(
                x=pd.to_datetime(df['time']),
                y=df['price'],
                mode='markers',
                marker=dict(
                    color=style['color'], 
                    size=style['size'], 
                    symbol=style['symbol'], 
                    line=dict(width=1, color='black')
                ),
                name=run_name,
                text=hover_text,
                hoverinfo='text'
            ),
            row=1, col=1
        )

    # 3. Trade Table
    table_data = []
    for df in all_trades:
        if df.empty: continue
        for _, t in df.iterrows():
            table_data.append([
                t['Run'],
                t['time'],
                t['ticker'],
                t['action'],
                f"{t['price']:.0f}¢",
                f"${t.get('pnl', 0):.2f}"
            ])
            
    # Sort by time
    table_data.sort(key=lambda x: x[1])
    
    if table_data:
        headers = ["Run", "Time", "Ticker", "Action", "Price", "PnL"]
        fig.add_trace(
            go.Table(
                header=dict(values=headers, fill_color='paleturquoise', align='left'),
                cells=dict(values=list(zip(*table_data)), fill_color='lavender', align='left')
            ),
            row=2, col=1
        )

    fig.update_layout(
        height=1000,
        title_text="Strategy Comparison: OG vs Filtered vs Unfiltered",
        hovermode="closest"
    )
    
    if not os.path.exists(CHARTS_DIR): os.makedirs(CHARTS_DIR)
    filename = os.path.join(CHARTS_DIR, "grand_comparison_dec17.html")
    fig.write_html(filename)
    print(f"Chart saved to: {filename}")

if __name__ == "__main__":
    generate_chart()
