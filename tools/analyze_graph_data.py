import re
import json
import os
import pandas as pd
import numpy as np
import sys
import warnings

# Suppress pandas warnings
warnings.filterwarnings("ignore")

def analyze_graph(file_path):
    print(f"Analyzing file: {file_path}")
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # Extract JSON data using regex
    def extract_data(name):
        # Look for: const name = [...];
        # We use a non-greedy match for the content inside brackets
        pattern = r"const " + name + r" = (\[.*?\]);"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for {name}: {e}")
                return []
        print(f"Warning: Could not find data for '{name}'")
        return []

    print("Extracting data...")
    reported = extract_data("reported") # Live ROI
    if not reported:
        reported = extract_data("live") # Live Cash

    local = extract_data("local")       # Backtest ROI
    if not local:
        local = extract_data("backtest") # Backtest Cash

    live_trades = extract_data("liveTrades")
    local_trades = extract_data("localTrades")

    print(f"Data extracted. Live points: {len(reported)}, Backtest points: {len(local)}")

    # 1. Trade Counts
    if live_trades or local_trades:
        print(f"\n1. Trade Counts:")
        print(f"   Live Trades: {len(live_trades)}")
        print(f"   Backtest Trades: {len(local_trades)}")
        
        if len(live_trades) == len(local_trades):
            print("   [MATCH] Trade counts are identical.")
        else:
            print(f"   [MISMATCH] Difference of {abs(len(live_trades) - len(local_trades))} trades.")
    else:
        print("\n1. Trade Counts: [N/A] No trade data found in this graph.")

    # 2. Equity Analysis
    if not reported or not local:
        print("\n[ERROR] Missing equity data series (reported or local is empty).")
        return

    try:
        # Convert to DataFrames
        df_live = pd.DataFrame(reported)
        df_backtest = pd.DataFrame(local)
        
        # Parse dates - assuming ISO format from the generator script
        # The generator uses .isoformat() which is typically "YYYY-MM-DDTHH:MM:SS.ffffff"
        df_live['time'] = pd.to_datetime(df_live['time'], format='ISO8601')
        df_backtest['time'] = pd.to_datetime(df_backtest['time'], format='ISO8601')
        
        # Sort
        df_live = df_live.sort_values('time')
        df_backtest = df_backtest.sort_values('time')

        # Determine value key (equity or cash)
        val_key_live = 'equity' if 'equity' in df_live.columns else 'cash'
        val_key_backtest = 'equity' if 'equity' in df_backtest.columns else 'cash'

        start_equity_live = df_live.iloc[0][val_key_live]
        end_equity_live = df_live.iloc[-1][val_key_live]
        
        start_equity_backtest = df_backtest.iloc[0][val_key_backtest]
        end_equity_backtest = df_backtest.iloc[-1][val_key_backtest]

        print(f"\n2. Performance ({val_key_live}):")
        print(f"   Live:     Start=${start_equity_live:.2f} -> End=${end_equity_live:.2f} (Change: ${end_equity_live - start_equity_live:.2f})")
        print(f"   Backtest: Start=${start_equity_backtest:.2f} -> End=${end_equity_backtest:.2f} (Change: ${end_equity_backtest - start_equity_backtest:.2f})")
        
        diff = end_equity_live - end_equity_backtest
        print(f"   Final Difference: ${diff:.2f}")

        # 3. Divergence Analysis
        print("\nCalculating divergence...")
        # Merge on nearest time
        merged = pd.merge_asof(df_live, df_backtest, on='time', suffixes=('_live', '_backtest'), direction='nearest', tolerance=pd.Timedelta('1s'))
        
        # Drop rows where we couldn't match (if any)
        merged = merged.dropna(subset=[f'{val_key_backtest}_backtest'])
        
        merged['diff'] = merged[f'{val_key_live}_live'] - merged[f'{val_key_backtest}_backtest']
        
        # Find max divergence
        max_diff = merged['diff'].abs().max()
        print(f"\n3. Divergence:")
        print(f"   Max Intraday Divergence: ${max_diff:.2f}")
        
        # Find first significant divergence (> $1.00)
        divergence_threshold = 1.0
        divergent_points = merged[merged['diff'].abs() > divergence_threshold]
        
        if not divergent_points.empty:
            first_div = divergent_points.iloc[0]
            print(f"   First significant divergence (> ${divergence_threshold}) at {first_div['time']}")
            print(f"   Live: ${first_div[f'{val_key_live}_live']:.2f} vs Backtest: ${first_div[f'{val_key_backtest}_backtest']:.2f}")
            print(f"   Diff: ${first_div['diff']:.2f}")
        else:
            print("   [GOOD] No significant divergence found (all within $1.00).")

    except Exception as e:
        print(f"\n[CRITICAL ERROR] Failed during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\backtest_charts\shadow_vs_local_roi_timeline.html"
    
    analyze_graph(file_path)
