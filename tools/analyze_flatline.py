import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

def analyze_activity(variant_dir, label):
    trades_path = Path(variant_dir) / "unified_trades.csv"
    if not trades_path.exists():
        print(f"No trades file for {label}")
        return

    df = pd.read_csv(trades_path)
    df['time'] = pd.to_datetime(df['time'])
    
    # Filter for Dec 2025 and Jan 2026
    df = df[df['time'] >= '2025-12-01']
    
    # Resample to daily trade counts
    daily_counts = df.set_index('time').resample('D').size()
    
    print(f"\n--- {label} Daily Trade Counts (Dec 20 - Jan 11) ---")
    print(daily_counts['2025-12-20':])
    
    # Check if it was holding positions during the flatline
    # This is harder to do perfectly without re-running the engine, 
    # but we can check if it was just buying or just selling.

def main():
    base_dir = Path("unified_engine_comparison_dec05")
    
    variants = [
        ("grid_r80_n20_m6_t10_s2", "Teal (Recommended)"),
        ("grid_r100_n20_m8_t10_s2", "Purple (User Fav)")
    ]
    
    for folder, name in variants:
        analyze_activity(base_dir / folder, name)

if __name__ == "__main__":
    main()
