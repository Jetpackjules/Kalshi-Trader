import argparse
import csv
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def load_first_ticks(gate_dir: Path, day_boundary_hour: int) -> dict[str, dict]:
    equity_path = gate_dir / "equity_history.csv"
    if not equity_path.exists():
        raise FileNotFoundError(f"Missing equity_history.csv in {gate_dir}")
    first_per_day: dict[str, dict] = {}
    with equity_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row.get("date")
            if not ts:
                continue
            day = ts[:10]
            if day_boundary_hour:
                try:
                    dt = datetime.fromisoformat(ts)
                    day = (dt - timedelta(hours=day_boundary_hour)).date().isoformat()
                except ValueError:
                    pass
            if day not in first_per_day:
                first_per_day[day] = row
    return first_per_day


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily restart backtests with progress.")
    parser.add_argument("--gate-dir", required=True, help="Gate run directory (with equity_history.csv)")
    parser.add_argument("--baseline-dir", required=True, help="Baseline run directory")
    parser.add_argument("--restart-prefix", required=True, help="Restart output prefix directory")
    parser.add_argument("--out", required=True, help="Output HTML path")
    parser.add_argument("--title", required=True, help="Graph title")
    parser.add_argument("--baseline-label", default="Current $100", help="Baseline label")
    parser.add_argument("--gate-label", default="Current $100 gated", help="Gate label")
    parser.add_argument("--bar-source-label", default="Current $100", help="Bar source label")
    parser.add_argument("--bar-mode", default="returns", choices=["returns", "trades", "both"])
    parser.add_argument("--trade-subplot", default="none", choices=["none", "label", "all"])
    parser.add_argument("--trade-source-label", default="", help="Label to use for trade-count subplot")
    parser.add_argument("--snapshot", default="dec05_snapshot.json", help="Snapshot path")
    parser.add_argument("--strategy", default="recommended_live_strategy", help="Strategy name")
    parser.add_argument(
        "--strategy-kwargs",
        default="",
        help="JSON string of extra strategy kwargs (passed to run_unified_backtest.py)",
    )
    parser.add_argument("--warmup-hours", type=int, default=0, help="Warmup hours")
    parser.add_argument(
        "--day-boundary-hour",
        type=int,
        default=0,
        help="Hour offset for daily boundaries (e.g. 5 means day runs 5am->5am)",
    )
    parser.add_argument("--force", action="store_true", help="Re-run even if output exists")
    args = parser.parse_args()

    gate_dir = Path(args.gate_dir)
    baseline_dir = Path(args.baseline_dir)
    restart_prefix = Path(args.restart_prefix)
    out_path = Path(args.out)

    first_per_day = load_first_ticks(gate_dir, args.day_boundary_hour)
    days = sorted(first_per_day.keys())
    total = len(days)
    if total == 0:
        raise SystemExit("No days found in gate equity history.")

    failures = []
    for idx, day in enumerate(days, start=1):
        row = first_per_day[day]
        cash = float(row.get("cash") or 0.0)
        dt = datetime.fromisoformat(row["date"])
        ts_sec = dt.strftime("%Y-%m-%d %H:%M:%S")
        out_dir = Path(f"{restart_prefix}{day.replace('-', '')}")
        equity_file = out_dir / "equity_history.csv"
        if equity_file.exists() and not args.force:
            pct = (idx / total) * 100.0
            print(f"[{idx}/{total} | {pct:5.1f}%] Skip {day} (exists)")
            continue
        pct = (idx / total) * 100.0
        print(f"[{idx}/{total} | {pct:5.1f}%] Run {day} cash={cash:.2f} start={ts_sec}")
        cmd = [
            sys.executable,
            "run_unified_backtest.py",
            "--snapshot",
            args.snapshot,
            "--start-ts",
            ts_sec,
            "--initial-cash",
            f"{cash}",
            "--strategy",
            args.strategy,
            "--out-dir",
            str(out_dir),
            "--warmup-hours",
            str(args.warmup_hours),
            "--day-boundary-hour",
            str(args.day_boundary_hour),
            "--quiet",
        ]
        if args.strategy_kwargs and args.strategy_kwargs != "{}":
            cmd.extend(["--strategy-kwargs", args.strategy_kwargs])
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            failures.append((day, exc.returncode))
            print(f"[{idx}/{total}] ERROR {day} (exit={exc.returncode})")
            continue

    plot_args = [
        sys.executable,
        "tools/generate_best_vs_current_roi_graph.py",
        "--out-dir",
        str(baseline_dir),
        "--label",
        args.baseline_label,
        "--out-dir",
        str(gate_dir),
        "--label",
        args.gate_label,
    ]
    for day in days:
        out_dir = Path(f"{restart_prefix}{day.replace('-', '')}")
        plot_args.extend(["--out-dir", str(out_dir), "--label", f"Restart {day}"])
    plot_args.extend(
        [
            "--out",
            str(out_path),
            "--title",
            args.title,
            "--bar-source-label",
            args.bar_source_label,
            "--bar-mode",
            args.bar_mode,
        ]
    )
    if args.trade_subplot != "none":
        plot_args.extend(["--trade-subplot", args.trade_subplot])
    if args.trade_source_label:
        plot_args.extend(["--trade-source-label", args.trade_source_label])
    subprocess.run(plot_args, check=True)
    print(f"Wrote {out_path}")
    if failures:
        print("Failed days:")
        for day, code in failures:
            print(f"  {day} (exit={code})")


if __name__ == "__main__":
    main()
