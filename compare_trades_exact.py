import pandas as pd
import os

def load_trades(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return pd.DataFrame()
    
    df = pd.read_csv(file_path)
    # Normalize columns
    df.columns = [c.strip().lower() for c in df.columns]
    
    # Parse timestamps
    if 'timestamp' in df.columns:
        df['datetime'] = pd.to_datetime(df['timestamp'])
    elif 'time' in df.columns:
        df['datetime'] = pd.to_datetime(df['time'])
        
    return df

def compare_side_by_side(real_df, sim_df, date_str):
    print(f"\n=== SIDE-BY-SIDE COMPARISON FOR {date_str} ===")
    
    # Filter by date
    real_day = real_df[real_df['datetime'].dt.strftime('%Y-%m-%d') == date_str].copy()
    sim_day = sim_df[sim_df['datetime'].dt.strftime('%Y-%m-%d') == date_str].copy()
    
    if real_day.empty and sim_day.empty:
        print("No trades found for this date.")
        return

    # Add source column
    real_day['source_log'] = 'REAL'
    sim_day['source_log'] = 'SIM'
    
    # Combine and sort
    combined = pd.concat([real_day, sim_day])
    combined.sort_values(['ticker', 'datetime'], inplace=True)
    
    # Iterate by ticker to show flow
    tickers = combined['ticker'].unique()
    
    for t in tickers:
        print(f"\n--- {t} ---")
        t_df = combined[combined['ticker'] == t]
        
        # Print header
        print(f"{'Time':<25} {'Source':<5} {'Action':<8} {'Qty':<4} {'Price':<6} {'Cost':<8}")
        print("-" * 65)
        
        for _, row in t_df.iterrows():
            print(f"{row['datetime'].strftime('%H:%M:%S.%f'):<25} {row['source_log']:<5} {row['action']:<8} {row['qty']:<4} {row['price']:<6} {row['cost']:<8.2f}")

if __name__ == "__main__":
    real_path = "live_trading_system/vm_logs/trades.csv"
    sim_path = "backtest_trades.csv"
    
    real_df = load_trades(real_path)
    sim_df = load_trades(sim_path)
    
    if not real_df.empty and not sim_df.empty:
        compare_side_by_side(real_df, sim_df, "2025-12-24")
        compare_side_by_side(real_df, sim_df, "2025-12-25")
