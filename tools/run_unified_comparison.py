import argparse
import os
import subprocess
import sys
from pathlib import Path

def run_command(cmd):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"Error: Command failed with exit code {result.returncode}")
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="Run multiple Unified Engine backtest variants and compare them.")
    parser.add_argument("--snapshot", type=str, required=True, help="Path to starting snapshot")
    parser.add_argument("--start-ts", type=str, default="2025-12-05 00:00:00", help="Start timestamp")
    parser.add_argument("--initial-cash", type=float, default=1000.0, help="Initial cash")
    parser.add_argument("--out", type=str, default="backtest_charts/unified_comparison_variants.html", help="Output HTML path")
    args = parser.parse_args()

    # Define variants to run
    # Format: (strategy_func_name, enable_time_constraints, label)
    variants = [
        ("baseline_v3", True, "v3_baseline (hours)"),
        ("baseline_v3", False, "v3_baseline (all-day)"),
        ("hb_notional_010", True, "hb_notional_010 (hours)"),
        ("hb_notional_010", False, "hb_notional_010 (all-day)"),
        ("hb_risk_090", True, "hb_risk_090 (hours)"),
        ("hb_risk_090", False, "hb_risk_090 (all-day)"),
    ]

    base_out_dir = Path("unified_engine_comparison")
    base_out_dir.mkdir(exist_ok=True)

    graph_cmd = [
        "python", "tools/generate_unified_variant_graph.py",
        "--snapshot", args.snapshot,
        "--out", args.out
    ]

    for strat, hours, label in variants:
        dir_name = label.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "")
        out_dir = base_out_dir / dir_name
        
        # Run Backtest
        cmd = [
            "python", "run_unified_backtest.py",
            "--snapshot", args.snapshot,
            "--start-ts", f'"{args.start_ts}"',
            "--initial-cash", str(args.initial_cash),
            "--warmup-hours", "0",
            "--out-dir", str(out_dir),
            "--strategy", strat
        ]
        if not hours:
            cmd.append("--trade-all-day")
            
        if not run_command(" ".join(cmd)):
            print(f"Aborting due to failure in variant {label}")
            return

        graph_cmd.extend(["--out-dir", str(out_dir), "--label", f'"{label}"'])

    # Generate Graph
    run_command(" ".join(graph_cmd))
    print(f"\nAll variants complete. Comparison graph: {args.out}")

if __name__ == "__main__":
    main()
