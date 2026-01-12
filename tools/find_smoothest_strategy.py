import pandas as pd
from pathlib import Path
import numpy as np

def analyze_smoothness(variant_dir, label):
    equity_path = Path(variant_dir) / "equity_history.csv"
    if not equity_path.exists():
        return None

    try:
        df = pd.read_csv(equity_path)
        df['date'] = pd.to_datetime(df['date'], format='mixed')
        df = df.sort_values('date')
        
        # Resample to daily
        daily = df.set_index('date').resample('D').last().dropna()
        
        if len(daily) < 10:
            return None
            
        daily['return'] = daily['equity'].pct_change().fillna(0)
        
        # Metrics
        total_days = len(daily)
        
        # Win Rate: Days with > 0.05% return (ignoring tiny noise)
        winning_days = (daily['return'] > 0.0005).sum()
        win_rate = winning_days / total_days
        
        # Flatline: Days with < 0.05% absolute return
        flat_days = (daily['return'].abs() < 0.0005).sum()
        flat_rate = flat_days / total_days
        
        # Recent Trend (Last 7 days)
        last_7_days = daily.iloc[-7:]
        if len(last_7_days) > 0:
            recent_return = (last_7_days['equity'].iloc[-1] / last_7_days['equity'].iloc[0]) - 1
        else:
            recent_return = 0
            
        # Max Drawdown Duration (Days)
        cumulative = (1 + daily['return']).cumprod()
        peak = cumulative.expanding(min_periods=1).max()
        drawdown = (cumulative / peak) - 1
        
        # Calculate max duration in drawdown
        is_in_drawdown = drawdown < 0
        # Group consecutive True values
        drawdown_periods = is_in_drawdown.astype(int).groupby(is_in_drawdown.ne(is_in_drawdown.shift()).cumsum()).cumsum()
        # Filter only where is_in_drawdown is True
        drawdown_lengths = drawdown_periods[is_in_drawdown]
        if not drawdown_lengths.empty:
            max_drawdown_duration = drawdown_lengths.max()
        else:
            max_drawdown_duration = 0
            
        # Total Return
        total_return = (daily['equity'].iloc[-1] / daily['equity'].iloc[0]) - 1

        return {
            'Label': label,
            'Win Rate': win_rate,
            'Flat Rate': flat_rate,
            'Recent Return': recent_return,
            'Max Drawdown Duration': max_drawdown_duration,
            'Total Return': total_return,
            'Final Equity': daily['equity'].iloc[-1]
        }
        
    except Exception as e:
        # print(f"Error analyzing {label}: {e}")
        return None

def main():
    results_dir = Path("unified_engine_comparison_dec05")
    all_stats = []
    
    print("Analyzing strategies for smoothness...")
    
    # Load manifest to get labels
    manifest_path = results_dir / "manifest.json"
    import json
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
        
    total = len(manifest)
    for i, item in enumerate(manifest, 1):
        if i % 10 == 0:
            print(f"[{i}/{total}] Processing {item['label']}...", flush=True)
        stats = analyze_smoothness(item['out_dir'], item['label'])
        if stats:
            all_stats.append(stats)
            
    df = pd.DataFrame(all_stats)
    
    # Filter: Must have positive recent return (no downward trend at end)
    df_filtered = df[df['Recent Return'] > 0].copy()
    
    # Filter out the "purple" clone (approx 1080.05)
    df_filtered = df_filtered[abs(df_filtered['Final Equity'] - 1080.05) > 1.0]
    
    # Score: High Win Rate, Low Flat Rate, Low Drawdown Duration
    # Normalize metrics
    df_filtered['Score'] = (
        (df_filtered['Win Rate'] * 2.0) - 
        (df_filtered['Flat Rate'] * 1.0) - 
        (df_filtered['Max Drawdown Duration'] / df_filtered['Max Drawdown Duration'].max() * 0.5) +
        (df_filtered['Total Return'] / df_filtered['Total Return'].max() * 0.5)
    )
    
    df_filtered = df_filtered.sort_values('Score', ascending=False)
    
    print("\nTop 10 'Smoothest' Strategies (Positive Recent Trend):")
    cols = ['Label', 'Win Rate', 'Flat Rate', 'Recent Return', 'Max Drawdown Duration', 'Total Return', 'Final Equity']
    print(df_filtered[cols].head(10).to_string(index=False))
    
    # Also print the stats for the user's rejected strategies for comparison
    print("\nComparison with Rejected Strategies:")
    rejected = ['grid_r80_n20_m6_t10_s2', 'grid_r100_n20_m8_t10_s2']
    print(df[df['Label'].isin(rejected)][cols].to_string(index=False))

if __name__ == "__main__":
    main()
