import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run_command(cmd, show_command=False):
    if show_command:
        print(f"Running: {cmd}", flush=True)
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"Error: Command failed with exit code {result.returncode}", flush=True)
    return result.returncode == 0


def _parse_loss_pcts(raw: str) -> list[float]:
    if not raw:
        return []
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(float(part))
        except ValueError:
            continue
    return values


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--:--"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def _snapshot_timestamp(snapshot: dict) -> str | None:
    raw = snapshot.get("last_update") or snapshot.get("timestamp") or snapshot.get("snapshot_time")
    if not raw:
        return None
    if isinstance(raw, str):
        m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})", raw)
        if m:
            return f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}"
        return raw
    return None

def main():
    parser = argparse.ArgumentParser(description="Run multiple Unified Engine backtest variants and compare them.")
    parser.add_argument("--snapshot", type=str, required=True, help="Path to starting snapshot")
    parser.add_argument(
        "--start-ts",
        type=str,
        default="",
        help="Start timestamp (defaults to snapshot timestamp)",
    )
    parser.add_argument(
        "--initial-cash",
        type=float,
        default=None,
        help="Initial cash (defaults to snapshot balance)",
    )
    parser.add_argument("--out", type=str, default="backtest_charts/unified_comparison_variants.html", help="Output HTML path")
    parser.add_argument(
        "--preset",
        type=str,
        default="new-only",
        choices=["full", "loss-sweep", "new-only", "comprehensive", "recommended-hours-check"],
        help="Variant set to run (ignored if --only-strategy is set)",
    )
    parser.add_argument(
        "--only-strategy",
        type=str,
        default="",
        help="Run only this strategy (function name). Comma-separated for multiple.",
    )
    parser.add_argument(
        "--loss-pcts",
        type=str,
        default="0.02,0.03,0.04",
        help="Comma-separated max_loss_pct values for loss-sweep",
    )
    parser.add_argument(
        "--include-all-day",
        action="store_true",
        help="Include all-day variants when supported",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--workers", type=int, default=16, help="Number of parallel workers")
    parser.add_argument(
        "--use-snapshot-start",
        action="store_true",
        help="Use snapshot timestamp for start-ts",
    )
    parser.add_argument(
        "--use-snapshot-balance",
        action="store_true",
        help="Use snapshot balance for initial cash",
    )
    parser.add_argument(
        "--warmup-hours",
        type=int,
        default=48,
        help="Hours of data to feed before start-ts",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default="unified_engine_comparison",
        help="Directory to store per-variant backtest results",
    )
    args = parser.parse_args()

    if args.use_snapshot_start or args.use_snapshot_balance or not args.start_ts or args.initial_cash is None:
        with open(args.snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        if args.use_snapshot_start or not args.start_ts:
            snap_ts = _snapshot_timestamp(snapshot)
            if snap_ts:
                args.start_ts = snap_ts
        if args.use_snapshot_balance or args.initial_cash is None:
            try:
                args.initial_cash = float(snapshot.get("balance") or 0.0)
            except (TypeError, ValueError):
                pass

    label_overrides = {
        "baseline_v3": "v3_baseline",
        "tighter_gates_fewer_trades": "v3_tighter_gates",
        "looser_gates_more_trades": "v3_looser_gates",
        "conservative_sizing": "v3_conservative_size",
        "higher_budget_same_edges": "v3_higher_budget",
        "sniper_v3": "v3_sniper",
        "bargain_hunter_v3": "v3_bargain_hunter",
        "closer_v3": "v3_closer",
        "hybrid_v3": "v3_hybrid",
        "aggressive_reinvest_v3": "v3_aggressive",
        "kelly_v3": "v3_kelly",
    }

    # Define variants to run
    # Format: (strategy_func_name, enable_time_constraints, label, max_loss_pct, strategy_kwargs)
    only_strategies = [s.strip() for s in args.only_strategy.split(",") if s.strip()]
    if only_strategies:
        variants = []
        for strat in only_strategies:
            base_label = label_overrides.get(strat, strat)
            variants.append((strat, True, f"{base_label} (hours)", None, None))
            if args.include_all_day:
                variants.append((strat, False, f"{base_label} (all-day)", None, None))
    elif args.preset == "comprehensive":
        # Systematically explore the parameter space to break plateaus (~144 variants)
        risk_pcts = [0.8, 1.0]
        notional_pcts = [0.10, 0.15, 0.20]
        margins = [2.0, 4.0, 6.0, 8.0]
        tightness = [10, 25]
        scaling_factors = [2.0, 4.0, 6.0]
        
        variants = [
            ("baseline_v3", True, "v3_baseline", None, None),
            ("aggressive_reinvest_v3", True, "v3_aggressive", None, None),
            ("kelly_v3", True, "v3_kelly", None, None),
            ("hybrid_v3", True, "v3_hybrid", None, None),
        ]
        
        for r in risk_pcts:
            for n in notional_pcts:
                for m in margins:
                    for t in tightness:
                        for s in scaling_factors:
                            label = f"grid_r{int(r*100)}_n{int(n*100)}_m{int(m)}_t{t}_s{int(s)}"
                            kwargs = {
                                "name": label,
                                "risk_pct": r,
                                "max_notional_pct": n,
                                "margin_cents": m,
                                "tightness_percentile": t,
                                "scaling_factor": s,
                                "max_inventory": 150
                            }
                            variants.append(("generic_v3", True, label, None, kwargs))
    elif args.preset == "loss-sweep":
        loss_pcts = _parse_loss_pcts(args.loss_pcts)
        base = [
            ("baseline_v3", "v3_baseline"),
            ("tighter_gates_fewer_trades", "v3_tighter_gates"),
            ("conservative_sizing", "v3_conservative_size"),
            ("hb_notional_010", "hb_notional_010"),
            ("hb_risk_060", "hb_risk_060"),
        ]
        variants = []
        for strat, base_label in base:
            for pct in loss_pcts:
                label = f"{base_label} (hours, loss {pct:.2f})"
                variants.append((strat, True, label, pct, None))
            if args.include_all_day:
                for pct in loss_pcts:
                    label = f"{base_label} (all-day, loss {pct:.2f})"
                    variants.append((strat, False, label, pct, None))
    elif args.preset == "new-only":
        variants = [
            ("sniper_v3", True, "v3_sniper (hours)", None, None),
            ("bargain_hunter_v3", True, "v3_bargain_hunter (hours)", None, None),
            ("closer_v3", True, "v3_closer (hours)", None, None),
            ("hybrid_v3", True, "v3_hybrid (hours)", None, None), # The new adaptive strategy
            ("aggressive_reinvest_v3", True, "v3_aggressive (hours)", None, None),
            ("kelly_v3", True, "v3_kelly (hours)", None, None),
            ("kelly_v3", True, "v3_kelly (hours)", None, None),
        ]
    elif args.preset == "recommended-hours-check":
        label = "grid_r80_n10_m8_t10_s2"
        kwargs = {
            "name": label,
            "risk_pct": 0.8,
            "max_notional_pct": 0.10,
            "margin_cents": 8.0,
            "tightness_percentile": 10,
            "scaling_factor": 2.0,
            "max_inventory": 150
        }
        variants = [
            ("generic_v3", True, f"{label} (hours)", None, kwargs),
        ]
        if args.include_all_day:
            variants.append(("generic_v3", False, f"{label} (all-day)", None, kwargs))
    else:
        variants = [
            ("baseline_v3", True, "v3_baseline (hours)", None, None),
            ("hb_notional_010", True, "hb_notional_010 (hours)", None, None),
            ("hb_risk_060", True, "hb_risk_060 (hours)", None, None),
            ("hb_risk_090", True, "hb_risk_090 (hours)", None, None),
            ("hb_notional_010_risk_040", True, "hb_notional_010_risk_040 (hours)", None, None),
            ("hb_notional_010_risk_060", True, "hb_notional_010_risk_060 (hours)", None, None),
            ("hb_notional_010_risk_080", True, "hb_notional_010_risk_080 (hours)", None, None),
            ("hb_notional_010_risk_100", True, "hb_notional_010_risk_100 (hours)", None, None),
            ("conservative_sizing", True, "v3_conservative_size (hours)", None, None),
            ("tighter_gates_fewer_trades", True, "v3_tighter_gates (hours)", None, None),
            ("looser_gates_more_trades", True, "v3_looser_gates (hours)", None, None),
            ("baseline_v3", False, "v3_baseline (all-day)", None, None),
            ("hb_notional_010", False, "hb_notional_010 (all-day)", None, None),
            ("hb_risk_060", False, "hb_risk_060 (all-day)", None, None),
            ("hb_risk_090", False, "hb_risk_090 (all-day)", None, None),
            ("hb_notional_010_risk_040", False, "hb_notional_010_risk_040 (all-day)", None, None),
            ("hb_notional_010_risk_060", False, "hb_notional_010_risk_060 (all-day)", None, None),
            ("hb_notional_010_risk_080", False, "hb_notional_010_risk_080 (all-day)", None, None),
            ("hb_notional_010_risk_100", False, "hb_notional_010_risk_100 (all-day)", None, None),
            ("conservative_sizing", False, "v3_conservative_size (all-day)", None, None),
            ("tighter_gates_fewer_trades", False, "v3_tighter_gates (all-day)", None, None),
            ("looser_gates_more_trades", False, "v3_looser_gates (all-day)", None, None),
            ("higher_budget_same_edges", True, "v3_higher_budget (hours)", None, None),
            ("hb_notional_010_uncapped", True, "hb_notional_010_uncapped (hours)", None, None),
            ("hb_loss_040", True, "hb_loss_040 (hours)", None, None),
            ("higher_budget_same_edges", False, "v3_higher_budget (all-day)", None, None),
            ("hb_notional_010_uncapped", False, "hb_notional_010_uncapped (all-day)", None, None),
            ("hb_loss_040", False, "hb_loss_040 (all-day)", None, None),
            ("sniper_v3", True, "v3_sniper (hours)", None, None),
            ("bargain_hunter_v3", True, "v3_bargain_hunter (hours)", None, None),
            ("closer_v3", True, "v3_closer (hours)", None, None),
        ]

    base_out_dir = Path(args.results_dir)
    base_out_dir.mkdir(exist_ok=True)

    graph_cmd = [
        "python", "tools/generate_unified_variant_graph.py",
        "--snapshot", args.snapshot,
        "--out", args.out
    ]

    total = len(variants)
    print(f"Running {total} variants with {args.workers} workers...")
    
    import concurrent.futures

    def run_variant(variant_data):
        idx, (strat, hours, label, max_loss_pct, strat_kwargs) = variant_data
        
        dir_name = label.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "")
        out_dir = base_out_dir / dir_name
        
        # Skip if already exists and has results
        if (out_dir / "equity_history.csv").exists():
            if args.verbose:
                print(f"Skipping {label} (already exists)")
            return True, label, out_dir, 0.0

        if out_dir.exists():
            try:
                shutil.rmtree(out_dir)
            except PermissionError:
                suffix = time.strftime("%Y%m%d_%H%M%S", time.localtime())
                out_dir = base_out_dir / f"{dir_name}_{suffix}"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Run Backtest
        cmd = [
            "python", "run_unified_backtest.py",
            "--snapshot", args.snapshot,
            "--start-ts", f'"{args.start_ts}"',
            "--initial-cash", str(args.initial_cash),
            "--warmup-hours", str(args.warmup_hours),
            "--out-dir", str(out_dir),
            "--strategy", strat
        ]
        if max_loss_pct is not None:
            cmd.extend(["--max-loss-pct", str(max_loss_pct)])
        if strat_kwargs:
            # Pass as JSON string
            kwargs_json = json.dumps(strat_kwargs).replace('"', '\\"')
            cmd.extend(["--strategy-kwargs", f'"{kwargs_json}"'])
        if not hours:
            cmd.append("--trade-all-day")
            
        # Progress Bar Logic:
        # The user wants to see the progress of the FIRST process as a proxy for the whole batch.
        # So we enable --verbose for idx 1, and --quiet for everyone else.
        if idx == 1:
            pass # Default is standard output (progress bar enabled)
        else:
            cmd.append("--quiet")
            
        start_t = time.perf_counter()
        success = run_command(" ".join(cmd), show_command=args.verbose)
        duration = time.perf_counter() - start_t
        
        return success, label, out_dir, duration

    manifest_data = []
    # Run in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_variant, (i, v)): v for i, v in enumerate(variants, 1)}
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            success, label, out_dir, duration = future.result()
            
            status = "DONE" if success else "FAIL"
            print(f"[{completed}/{total}] {status} {label} ({_format_duration(duration)})", flush=True)
            
            if success:
                manifest_data.append({"out_dir": str(out_dir), "label": label})

    # Generate Graph
    print("Generating comparison graph...")
    manifest_path = base_out_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)

    graph_cmd = [
        "python", "tools/generate_unified_variant_graph.py",
        "--snapshot", args.snapshot,
        "--out", args.out,
        "--manifest", str(manifest_path)
    ]
    
    run_command(" ".join(graph_cmd), show_command=args.verbose)
    print(f"\nAll variants complete. Comparison graph: {args.out}", flush=True)

if __name__ == "__main__":
    main()
