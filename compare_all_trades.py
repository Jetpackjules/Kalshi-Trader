import pandas as pd
from datetime import datetime, timedelta

BACKTEST_FILE = "backtest_trades.csv"
LIVE_FILE = "live_trading_system/vm_logs/trades.csv"
START_TIME = "2026-01-01 00:00:00"

def load_and_filter(filepath, is_live=False):
    try:
        df = pd.read_csv(filepath)
        # Normalize column names
        if 'timestamp' in df.columns:
            df['time'] = pd.to_datetime(df['timestamp'])
        elif 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            
        # Filter by start time
        df = df[df['time'] >= START_TIME].copy()
        
        # Sort
        df = df.sort_values('time')
        return df
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return pd.DataFrame()

def aggregate_trades(df):
    """Aggregates trades for the same ticker/action within 1 minute."""
    if df.empty: return df
    
    aggregated = []
    
    # Group by Ticker + Action
    # Then iterate and merge close timestamps
    
    # Simple approach: Iterate and merge if same ticker/action and time < 60s diff
    current_group = None
    
    for _, row in df.iterrows():
        if current_group is None:
            current_group = row.to_dict()
            continue
            
        # Check match
        same_ticker = row['ticker'] == current_group['ticker']
        same_action = row['action'] == current_group['action']
        time_diff = (row['time'] - current_group['time']).total_seconds()
        
        if same_ticker and same_action and time_diff < 60:
            # Merge
            current_group['qty'] += row['qty']
            # Weighted average price? Or just keep first/last?
            # Let's do weighted avg for price
            total_val = (current_group['price'] * (current_group['qty'] - row['qty'])) + (row['price'] * row['qty'])
            current_group['price'] = total_val / current_group['qty']
            # Keep latest time
            current_group['time'] = row['time'] 
        else:
            aggregated.append(current_group)
            current_group = row.to_dict()
            
    if current_group:
        aggregated.append(current_group)
        
    return pd.DataFrame(aggregated)

def compare():
    print("--- Loading Trades ---")
    bt_df = load_and_filter(BACKTEST_FILE)
    live_df = load_and_filter(LIVE_FILE, is_live=True)
    
    print(f"Backtest Trades (Raw): {len(bt_df)}")
    print(f"Live Trades (Raw):     {len(live_df)}")
    
    # Aggregate Live Trades (since bot chunks orders)
    live_agg = aggregate_trades(live_df)
    print(f"Live Trades (Aggregated): {len(live_agg)}")
    
    print("\n--- COMPARISON (Aggregated Live vs Backtest) ---")
    print(f"{'Time':<20} | {'Source':<8} | {'Ticker':<25} | {'Action':<7} | {'Price':<6} | {'Qty':<4}")
    print("-" * 85)
    
    # Merge and Sort for display
    bt_df['Source'] = 'BACKTEST'
    live_agg['Source'] = 'LIVE'
    
    combined = pd.concat([bt_df, live_agg])
    combined = combined.sort_values('time')
    
    for _, row in combined.iterrows():
        t_str = row['time'].strftime("%H:%M:%S")
        price = f"{row['price']:.1f}"
        print(f"{t_str:<20} | {row['Source']:<8} | {row['ticker']:<25} | {row['action']:<7} | {price:<6} | {row['qty']:<4}")

if __name__ == "__main__":
    compare()
