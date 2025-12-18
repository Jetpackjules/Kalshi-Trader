import pandas as pd

def load_trades(filename, label):
    try:
        df = pd.read_csv(filename)
        df['Run'] = label
        return df
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return pd.DataFrame()

def compare_strategy(strat_name):
    print(f"\n=== Comparing Trades for Strategy: {strat_name} ===")
    
    df_unfiltered = load_trades('trades_unfiltered.csv', 'Unfiltered')
    df_5s = load_trades('trades_5s.csv', '5s Filter')
    df_1s = load_trades('trades_1s.csv', '1s Filter')
    
    dfs = [df_unfiltered, df_5s, df_1s]
    combined = pd.concat(dfs, ignore_index=True)
    
    print("Columns:", combined.columns.tolist())
    
    # Ensure pnl exists
    if 'pnl' not in combined.columns:
        combined['pnl'] = 0.0
    
    # Filter for strategy
    strat_trades = combined[combined['strategy'].str.contains(strat_name, case=False, regex=False)]
    
    if strat_trades.empty:
        print("No trades found.")
        return

    # Group by Run and print summary
    print("\n--- Summary Stats (Entry Price) ---")
    summary = strat_trades.groupby('Run').agg({
        'price': ['count', 'mean', 'min', 'max'],
        'pnl': ['sum', 'mean']
    })
    print(summary)
    
    # Print first 10 trades for each
    print("\n--- First 10 Trades (Side-by-Side) ---")
    for run in ['Unfiltered', '5s Filter', '1s Filter']:
        print(f"\n[ {run} ]")
        run_trades = strat_trades[strat_trades['Run'] == run].head(10)
        if run_trades.empty:
            print("(No trades)")
        else:
            cols = ['time', 'ticker', 'action', 'price', 'pnl']
            # Handle missing 'time' vs 'timestamp'
            if 'timestamp' in run_trades.columns: cols[0] = 'timestamp'
            
            print(run_trades[cols].to_string(index=False))

if __name__ == "__main__":
    compare_strategy("Safe Baseline")
    compare_strategy("Sniper: Cheapest")
