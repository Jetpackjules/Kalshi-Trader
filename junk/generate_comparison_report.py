import pandas as pd
import plotly.graph_objects as go
import re
import os

LOG_FILE = "comparison_recent_full.txt"
OUTPUT_HTML = "strategy_comparison_chart.html"

def parse_log_file(filepath):
    data = []
    try:
        # Try UTF-8 first
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        # Fallback to UTF-16
        with open(filepath, 'r', encoding='utf-16') as f:
            lines = f.readlines()
            
    # Regex to capture: [Day End 25DEC05] StrategyName Equity: $105.00
    # Note: Strategy names might have spaces.
    # Pattern: [Day End DATE] STRATEGY Equity: $VALUE (Cash
    pattern = re.compile(r"\[Day End (\d{2}[A-Z]{3}\d{2})\] (.*?) Equity: \$([\d\.]+)")
    
    for line in lines:
        match = pattern.search(line)
        if match:
            date_str = match.group(1)
            strategy = match.group(2).strip()
            equity = float(match.group(3))
            data.append({'Date': date_str, 'Strategy': strategy, 'Equity': equity})
            
    return pd.DataFrame(data)

def generate_report():
    if not os.path.exists(LOG_FILE):
        print(f"Log file {LOG_FILE} not found.")
        return

    df = parse_log_file(LOG_FILE)
    if df.empty:
        print("No 'Day End' data found yet.")
        return

    # Pivot to get Strategies as columns
    df_pivot = df.pivot(index='Date', columns='Strategy', values='Equity')
    
    # Sort by Date (needs parsing)
    # 25DEC05 -> datetime
    df_pivot.index = pd.to_datetime(df_pivot.index, format="%y%b%d")
    df_pivot.sort_index(inplace=True)
    
    # Calculate ROI (assuming $100 start)
    # Or just use Equity
    
    print("\n=== DAILY EQUITY TABLE ===")
    print(df_pivot.to_string())
    
    print("\n=== CUMULATIVE ROI TABLE (%) ===")
    roi_df = (df_pivot - 100.0) / 100.0 * 100.0
    print(roi_df.to_string(float_format="%.1f"))
    
    # Generate Chart
    fig = go.Figure()
    for col in df_pivot.columns:
        fig.add_trace(go.Scatter(x=df_pivot.index, y=df_pivot[col], mode='lines+markers', name=col))
        
    fig.update_layout(
        title="Strategy Comparison: Equity Curve (Dec 05 - Dec 28)",
        xaxis_title="Date",
        yaxis_title="Equity ($)",
        template="plotly_dark"
    )
    
    fig.write_html(OUTPUT_HTML)
    print(f"\nChart saved to {OUTPUT_HTML}")

if __name__ == "__main__":
    generate_report()
