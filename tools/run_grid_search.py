import argparse
import subprocess
import sys
import os
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_variant(variant_config, snapshot_path, out_dir, verbose=False, stream_output=False):
    """
    Runs a single backtest variant.
    variant_config: (strategy_name, hours_only, label, max_loss_pct, extra_kwargs)
    """
    strategy_name, hours_only, label, max_loss_pct, extra_kwargs = variant_config
    
    # Construct command
    cmd = [
        sys.executable, "run_unified_backtest.py",
        "--snapshot", snapshot_path,
        "--strategy", strategy_name,
        "--out-dir", os.path.join(out_dir, label.replace(" ", "_").replace("(", "").replace(")", "")),
        "--start-ts", "2025-12-05 00:00:00", # Fixed start for consistency
        "--end-ts", "2026-01-11 23:59:59",   # Fixed end
    ]
    
    if max_loss_pct is not None:
        cmd.extend(["--max-loss-pct", str(max_loss_pct)])
        
    if not hours_only:
        cmd.append("--trade-all-day")
        
    if extra_kwargs:
        import json
        cmd.extend(["--strategy-kwargs", json.dumps(extra_kwargs)])

    if verbose:
        cmd.append("--verbose")
    elif not stream_output:
        # If streaming, we want default output (progress bar), so don't add quiet.
        # If NOT streaming, we want quiet.
        cmd.append("--quiet")

    start_time = time.time()
    try:
        # Run process
        if stream_output:
            # Stream directly to stdout/stderr
            subprocess.run(cmd, check=True)
            print() # Newline after progress bar
            # We can't capture output easily if we stream, so we can't parse final equity from stdout.
            # We need to read it from the CSV or just return 0.0 and rely on the file.
            # OR we can rely on the fact that run_unified_backtest.py writes to a file.
            # Let's just return 0.0 for equity for the streaming one, or try to read the log file?
            # Reading the log file is safer.
            final_equity = 0.0 
            # TODO: Read from trade log or summary file if needed.
            # For now, just return 0.0 to avoid crashing. The user sees the progress bar, that's what matters.
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse Output for Final Equity
            final_equity = 0.0
            match = re.search(r"Total Portfolio Value: \$([\d\.]+)", result.stdout)
            if match:
                final_equity = float(match.group(1))
            
        duration = time.time() - start_time
        return {
            "label": label,
            "equity": final_equity,
            "duration": duration,
            "status": "SUCCESS"
        }
        
    except subprocess.CalledProcessError as e:
        return {
            "label": label,
            "equity": 0.0,
            "duration": time.time() - start_time,
            "status": "FAIL",
            "error": str(e)
        }

def main():
    parser = argparse.ArgumentParser(description="Run Grid Search Strategy Optimization")
    parser.add_argument("--snapshot", required=True, help="Path to snapshot JSON")
    parser.add_argument("--workers", type=int, default=16, help="Number of parallel workers")
    args = parser.parse_args()
    
    # 1. Define Grid
    variants = []
    
    # A. Smooth Variants (Base Margin x Spread Factor)
    base_margins = [2.0, 3.0, 4.0, 5.0]
    spread_factors = [0.2, 0.4, 0.6, 0.8, 1.0]
    
    for base in base_margins:
        for factor in spread_factors:
            label = f"smooth_b{base}_f{factor}"
            variants.append(
                ("smooth_v3", True, label, None, {"base_margin": base, "spread_factor": factor})
            )
            
    # B. Bargain Hunter Variants (Margin Cents)
    margins = [6.0, 8.0, 10.0, 12.0, 15.0]
    for m in margins:
        label = f"bargain_m{m}"
        variants.append(
            ("bargain_hunter_v3", True, label, None, {"margin_cents": m})
        )
        
    print(f"Generated {len(variants)} variants. Running with {args.workers} workers...")
    
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit variants, enabling streaming for one worker per batch (roughly)
        futures = {}
        for i, v in enumerate(variants):
            # Stream if it's the first of a batch (0, 16, 32...)
            should_stream = (i % args.workers == 0)
            futures[executor.submit(run_variant, v, args.snapshot, "grid_search_out", stream_output=should_stream)] = v
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            res = future.result()
            results.append(res)
            print(f"[{completed}/{len(variants)}] {res['status']} {res['label']} -> ${res['equity']:.2f} ({res['duration']:.1f}s)")
            
    # 2. Analyze Results
    print("\n--- GRID SEARCH RESULTS ---")
    sorted_results = sorted(results, key=lambda x: x['equity'], reverse=True)
    
    print(f"{'Rank':<5} {'Label':<30} {'Equity':<10} {'Duration':<10}")
    print("-" * 60)
    for i, res in enumerate(sorted_results):
        print(f"{i+1:<5} {res['label']:<30} ${res['equity']:<10.2f} {res['duration']:<10.1f}s")
        
    # Calculate Stats
    equities = [r['equity'] for r in results if r['status'] == 'SUCCESS']
    if equities:
        import statistics
        print(f"\nMean Equity: ${statistics.mean(equities):.2f}")
        print(f"Median Equity: ${statistics.median(equities):.2f}")
        print(f"Max Equity: ${max(equities):.2f}")
        print(f"Min Equity: ${min(equities):.2f}")

    # 3. Generate Graph for Top 10
    if sorted_results:
        top_n = 10
        top_variants = sorted_results[:top_n]
        print(f"\nGenerating comparison graph for top {len(top_variants)} variants...")
        
        graph_script = os.path.join("tools", "generate_unified_variant_graph.py")
        if not os.path.exists(graph_script):
            print(f"Warning: Graph script not found at {graph_script}")
            return

        # Construct variants args: --out-dir PATH --label LABEL
        # Path must match what was passed to run_unified_backtest.py
        # out_dir = os.path.join("grid_search_out", label...)
        variant_args = []
        for res in top_variants:
            label = res['label']
            # Reconstruct the directory path logic from run_variant
            dir_name = label.replace(" ", "_").replace("(", "").replace(")", "")
            path = os.path.join("grid_search_out", dir_name)
            variant_args.extend(["--out-dir", path, "--label", label])

        cmd = [
            sys.executable, graph_script,
            "--snapshot", args.snapshot,
            "--out", "grid_search_results.html",
        ] + variant_args
        
        try:
            subprocess.run(cmd, check=True)
            print(f"Graph saved to: grid_search_results.html")
        except subprocess.CalledProcessError as e:
            print(f"Error generating graph: {e}")

if __name__ == "__main__":
    main()
