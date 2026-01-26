import subprocess
import re
import numpy as np

def run_tuning():
    # Range of probabilities to test
    probs = np.linspace(0.001, 0.05, 20) # 0.1% to 5%
    
    results = []
    
    print(f"Starting tuning sweep ({len(probs)} variants)...")
    
    for p in probs:
        cmd = [
            "python", "run_unified_backtest.py",
            "--strategy", "server_mirror.backtesting.strategies.simple_market_maker:simple_mm_fixed",
            "--strategy-kwargs", '{"qty": 10, "spread_cents": 4}',
            "--start-ts", "2026-01-21 00:00:00",
            "--snapshot", "vm_logs/snapshots/snapshot_2026-01-21_012019.json",
            "--fill-prob-per-min", str(p),
            "--quiet"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            output = result.stdout
            
            # Parse Equity
            # Look for "Total Portfolio Value: $X.XX" or "$-X.XX"
            match = re.search(r"Total Portfolio Value: \$([-\d\.]+)", output)
            if match:
                equity = float(match.group(1))
                print(f"Prob={p:.4f} -> Equity=${equity:.2f}")
                results.append((p, equity))
            else:
                print(f"Prob={p:.4f} -> Failed to parse equity")
                
        except Exception as e:
            print(f"Prob={p:.4f} -> Error: {e}")

    # Find best match for $20.28
    target = 20.28
    best_p = 0
    min_diff = float('inf')
    
    print("\n--- Results ---")
    for p, eq in results:
        diff = abs(eq - target)
        if diff < min_diff:
            min_diff = diff
            best_p = p
            
    print(f"\nBest Match: Prob={best_p:.4f} -> Equity=${dict(results)[best_p]:.2f} (Target: ${target})")

if __name__ == "__main__":
    run_tuning()
