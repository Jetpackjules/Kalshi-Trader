import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import pytz
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import os
import glob
from datetime import datetime, timedelta

# Configuration
LOG_DIR = r"C:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
OUTPUT_DIR = "charts"

def parse_date_from_filename(filename):
    # Format: market_data_KXHIGHNY-25DEC10.csv
    try:
        basename = os.path.basename(filename)
        # Extract "25DEC10"
        # Split by '-' -> ["market_data_KXHIGHNY", "25DEC10.csv"]
        date_part = basename.split('-')[-1].replace('.csv', '')
        # Parse "25DEC10" -> Year 25, Month DEC, Day 10
        dt = datetime.strptime(date_part, "%y%b%d")
        return dt
    except Exception as e:
        print(f"Skipping {filename}: {e}")
        return None

def generate_charts():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # Find all CSV files
    files = glob.glob(os.path.join(LOG_DIR, "market_data_*.csv"))
    
    # Parse dates and sort
    file_dates = []
    for f in files:
        dt = parse_date_from_filename(f)
        if dt:
            file_dates.append((dt, f))
    
    # Sort by date
    file_dates.sort(key=lambda x: x[0])
    
    # Take last 7 days (or fewer if not enough data)
    recent_files = file_dates[-7:]
    
    print(f"Found {len(file_dates)} logs. Generating charts for the last {len(recent_files)} days...")

    for dt, csv_file in recent_files:
        date_str = dt.strftime("%Y-%m-%d")
        output_file = os.path.join(OUTPUT_DIR, f"{date_str}.html")
        
        print(f"Processing {date_str}...")
        generate_single_chart(csv_file, output_file, date_str)

def generate_single_chart(csv_file, output_file, date_label):
    # ... (read csv logic remains same) ...
    try:
        df = pd.read_csv(csv_file, on_bad_lines='skip')
    except Exception as e:
        print(f"Error reading {csv_file}: {e}")
        return

    if df.empty:
        print("Dataframe is empty.")
        return

    # Convert timestamp (RAW - Naive)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp']
    
    # Extract Temp and Label
    def parse_ticker(ticker):
        try:
            parts = ticker.split('-')
            suffix = parts[-1]
            type_char = suffix[0]
            val_str = suffix[1:]
            val = float(val_str)
            label = f"{'≥' if type_char == 'T' else '<'}{val:.1f}°F"
            return label, val, type_char
        except:
            return ticker, 0, '?'

    df[['label', 'temp', 'type']] = df['market_ticker'].apply(
        lambda x: pd.Series(parse_ticker(x))
    )
    
    df['no_prob'] = pd.to_numeric(df['implied_no_ask'], errors='coerce')
    df = df.dropna(subset=['no_prob'])
    df = df.sort_values('date')

    # --- Plotting ---
    fig = make_subplots(
        rows=1, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.05,
        subplot_titles=(f"NO Probability - {date_label}",)
    )
    
    colors = px.colors.qualitative.Plotly
    labels = df['label'].unique()
    
    for i, label in enumerate(sorted(labels)):
        subset = df[df['label'] == label]
        fig.add_trace(
            go.Scatter(
                x=subset['date'], 
                y=subset['no_prob'],
                name=label,
                mode='lines',
                line=dict(color=colors[i % len(colors)], shape='hv'), # Step Chart: Horizontal-Vertical
                hovertemplate="%{y:.0f}<extra></extra>", # Show only value, no extra junk
                legendgroup="markets"
            ),
            row=1, col=1
        )
        
    # Market Hours
    try:
        if not df.empty:
            open_time = df['date'].min()
            close_time = df['date'].max()
            
            fig.add_vrect(
                x0=open_time, x1=close_time,
                fillcolor="green", opacity=0.05,
                layer="below", line_width=0,
                row=1, col=1
            )
            fig.add_vline(x=open_time, line_dash="dash", line_color="green", row=1, col=1)
            fig.add_vline(x=close_time, line_dash="dash", line_color="red", row=1, col=1)
    except Exception as e:
        print(f"Error adding annotations: {e}")

    fig.update_layout(
        height=800,
        # width=1200, # Not strictly needed for HTML, responsive is better
        hovermode="x unified",
        legend=dict(orientation="h", y=1.01, x=1, xanchor="right"),
        title_text=f"Market History - {date_label}"
    )
    
    fig.update_yaxes(title_text="NO Prob (%)", range=[0, 100], row=1, col=1)
    
    # Save as HTML (Instant)
    try:
        fig.write_html(output_file)
        print(f"Saved {output_file}")
    except Exception as e:
        print(f"Error saving HTML: {e}")

if __name__ == "__main__":
    generate_charts()
