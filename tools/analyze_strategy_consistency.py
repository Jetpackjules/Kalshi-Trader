import os
import pandas as pd
import numpy as np
from pathlib import Path
import argparse

def calculate_metrics(equity_df):
    # Ensure date is datetime
    equity_df['date'] = pd.to_datetime(equity_df['date'], format='mixed')
    equity_df = equity_df.sort_values('date')
    
    # Resample to daily to ensure consistent periods
    # We take the last equity value of each day
    daily_df = equity_df.set_index('date').resample('D').last().dropna()
    
    # Calculate daily returns
    daily_df['return'] = daily_df['equity'].pct_change()
    daily_df = daily_df.dropna()
    
    if len(daily_df) < 2:
        return None

    # Metrics
    mean_return = daily_df['return'].mean()
    std_return = daily_df['return'].std()
    
    # Annualized Sharpe (assuming 365 trading days for crypto/prediction markets)
    sharpe = (mean_return / std_return) * np.sqrt(365) if std_return > 0 else 0
    
    # Sortino
    downside_returns = daily_df.loc[daily_df['return'] < 0, 'return']
    downside_std = downside_returns.std()
    sortino = (mean_return / downside_std) * np.sqrt(365) if downside_std > 0 else 0
    
    # Win Rate
    win_rate = (daily_df['return'] > 0).mean()
    
    # Max Drawdown
    cumulative_returns = (1 + daily_df['return']).cumprod()
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = (cumulative_returns / peak) - 1
    max_drawdown = drawdown.min()
    
    # Total Return
    total_return = (daily_df['equity'].iloc[-1] / daily_df['equity'].iloc[0]) - 1

    return {
        'Sharpe': sharpe,
        'Sortino': sortino,
        'Win Rate': win_rate,
        'Max Drawdown': max_drawdown,
        'Total Return': total_return,
        'Daily Volatility': std_return
    }

def main():
    parser = argparse.ArgumentParser(description="Analyze strategy consistency")
    parser.add_argument("--results-dir", type=str, required=True, help="Directory containing backtest results")
    args = parser.parse_args()
    
    results_dir = Path(args.results_dir)
    all_metrics = []
    
    print(f"Analyzing results in {results_dir}...")
    
    variants = list(results_dir.iterdir())
    total = len(variants)
    
    for i, variant_dir in enumerate(variants, 1):
        if i % 10 == 0:
            print(f"[{i}/{total}] Processing {variant_dir.name}...", flush=True)
            
        if not variant_dir.is_dir():
            continue
            
        equity_path = variant_dir / "equity_history.csv"
        if not equity_path.exists():
            continue
            
        try:
            df = pd.read_csv(equity_path)
            metrics = calculate_metrics(df)
            if metrics:
                metrics['Strategy'] = variant_dir.name
                all_metrics.append(metrics)
        except Exception as e:
            print(f"Error processing {variant_dir.name}: {e}")
            
    if not all_metrics:
        print("No valid results found.")
        return

    results_df = pd.DataFrame(all_metrics)
    
    # Sort by Sharpe Ratio
    results_df = results_df.sort_values('Sharpe', ascending=False)
    
    print("\nTop 20 Strategies by Sharpe Ratio (Consistency):")
    print(results_df[['Strategy', 'Sharpe', 'Win Rate', 'Max Drawdown', 'Total Return']].head(20).to_string(index=False))
    
    # Save to CSV
    results_df.to_csv(results_dir / "consistency_analysis.csv", index=False)
    print(f"\nFull analysis saved to {results_dir / 'consistency_analysis.csv'}")

if __name__ == "__main__":
    main()
