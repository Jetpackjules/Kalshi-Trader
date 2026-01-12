import pandas as pd
from pathlib import Path
import json

def get_final_equity(variant_dir):
    equity_path = Path(variant_dir) / "equity_history.csv"
    if not equity_path.exists():
        return 0.0
    
    try:
        df = pd.read_csv(equity_path)
        if df.empty: return 0.0
        return float(df.iloc[-1]['equity'])
    except:
        return 0.0

def main():
    results_dir = Path("unified_engine_comparison_dec05")
    manifest_path = results_dir / "manifest.json"
    
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
        
    target_equity = 1080.05
    matches = []
    
    print(f"Searching for strategies with final equity ~${target_equity}...")
    
    for item in manifest:
        equity = get_final_equity(item['out_dir'])
        if abs(equity - target_equity) < 0.1:
            matches.append((item['label'], equity))
            
    print(f"\nFound {len(matches)} matching strategies:")
    for label, eq in sorted(matches):
        print(f"- {label}: ${eq:.2f}")

if __name__ == "__main__":
    main()
