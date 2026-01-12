import subprocess
import json
import sys
from pathlib import Path

def main():
    kwargs = {
        "name": "grid_r80_n10_m8_t10_s2",
        "risk_pct": 0.8,
        "max_notional_pct": 0.1,
        "margin_cents": 8.0,
        "tightness_percentile": 10,
        "scaling_factor": 2.0,
        "max_inventory": 150
    }
    
    kwargs_json = json.dumps(kwargs)
    
    cmd = [
        sys.executable, "run_unified_backtest.py",
        "--snapshot", "vm_logs/snapshots/snapshot_2026-01-08_173738.json",
        "--start-ts", "2026-01-08 17:37:38",
        "--warmup-hours", "48",
        "--out-dir", "unified_engine_out_recommended",
        "--strategy", "generic_v3",
        "--strategy-kwargs", kwargs_json
    ]
    
    print(f"Running backtest for {kwargs['name']}...")
    
    # Clean output directory
    import shutil
    out_dir = Path("unified_engine_out_recommended")
    if out_dir.exists():
        print(f"Cleaning {out_dir}...")
        try:
            shutil.rmtree(out_dir, ignore_errors=True)
        except Exception as e:
            print(f"Warning: Could not fully clean {out_dir}: {e}")
        
    result = subprocess.run(cmd)
    
    if result.returncode != 0:
        print("Backtest failed!")
        sys.exit(result.returncode)
        
    print("Backtest complete.")

if __name__ == "__main__":
    main()
