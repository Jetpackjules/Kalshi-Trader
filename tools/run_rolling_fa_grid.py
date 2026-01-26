import argparse
import csv
import subprocess
import sys
from pathlib import Path

import plotly.graph_objects as go


def _read_avg_series(path: Path) -> tuple[list[str], list[float]] | None:
    if not path.exists():
        return None
    dates = []
    values = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get("start_date")
            val = row.get("avg_roi_per_day_pct")
            if not date or val is None:
                continue
            dates.append(date)
            values.append(float(val))
    if not dates:
        return None
    return dates, values


def _mean(values: list[float]) -> float:
    return sum(values) / max(len(values), 1)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rolling-start grid for famine/abundance combos.")
    parser.add_argument("--start-date", default="2025-12-04", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2026-01-13", help="End date (YYYY-MM-DD)")
    parser.add_argument("--f-max", type=int, default=5, help="Max famine days")
    parser.add_argument("--a-max", type=int, default=5, help="Max abundance days")
    parser.add_argument("--snapshot", default="dec05_snapshot.json", help="Snapshot path")
    parser.add_argument("--strategy", default="recommended_live_strategy_dec100", help="Strategy name")
    parser.add_argument("--strategy-kwargs", default="", help="JSON string of strategy kwargs")
    parser.add_argument("--initial-cash", type=float, default=100.0, help="Initial cash per run")
    parser.add_argument("--warmup-hours", type=int, default=0, help="Warmup hours before start")
    parser.add_argument("--day-boundary-hour", type=int, default=5, help="Day boundary hour")
    parser.add_argument("--workers", type=int, default=6, help="Workers per rolling run")
    parser.add_argument("--out-dir", default="backtest_charts", help="Output directory")
    parser.add_argument("--out-prefix", default="rolling_start_roi_dec04_dec100", help="Output prefix")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    csv_paths = []
    for f_days in range(1, args.f_max + 1):
        for a_days in range(1, args.a_max + 1):
            label = f"f{f_days}a{a_days}"
            out_csv = out_dir / f"{args.out_prefix}_{label}_5am.csv"
            out_html = out_dir / f"{args.out_prefix}_{label}_5am.html"
            out_prefix = f"unified_engine_comparison/{args.out_prefix}_{label}_5am_"

            cmd = [
                sys.executable,
                "tools/run_rolling_start_roi.py",
                "--start-date",
                args.start_date,
                "--end-date",
                args.end_date,
                "--snapshot",
                args.snapshot,
                "--strategy",
                args.strategy,
                "--initial-cash",
                str(args.initial_cash),
                "--warmup-hours",
                str(args.warmup_hours),
                "--day-boundary-hour",
                str(args.day_boundary_hour),
                "--famine-days",
                str(f_days),
                "--abundance-days",
                str(a_days),
                "--famine-daily-pct",
                "0",
                "--abundance-daily-pct",
                "0",
                "--out-prefix",
                out_prefix,
                "--out-csv",
                str(out_csv),
                "--out-html",
                str(out_html),
                "--skip-existing",
                "--workers",
                str(args.workers),
            ]
            if args.strategy_kwargs and args.strategy_kwargs != "{}":
                cmd.extend(["--strategy-kwargs", args.strategy_kwargs])
            subprocess.run(cmd, check=True)

            series = _read_avg_series(out_csv)
            if not series:
                continue
            _, values = series
            summary_rows.append(
                {
                    "combo": label,
                    "mean_avg_roi_per_day_pct": f"{_mean(values):.4f}",
                    "median_avg_roi_per_day_pct": f"{_median(values):.4f}",
                }
            )
            csv_paths.append((label, out_csv))

    summary_path = out_dir / f"{args.out_prefix}_fa_grid_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["combo", "mean_avg_roi_per_day_pct", "median_avg_roi_per_day_pct"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    fig = go.Figure()
    for label, path in csv_paths:
        series = _read_avg_series(path)
        if not series:
            continue
        dates, values = series
        mean_val = _mean(values)
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                mode="lines",
                name=f"{label} (mean={mean_val:.2f})",
            )
        )

    fig.update_layout(
        title="Rolling Start ROI (Avg per Day) - F/A Grid",
        xaxis=dict(title="Start date"),
        yaxis=dict(title="Avg ROI/day (%)"),
        legend=dict(orientation="h"),
        margin=dict(l=40, r=40, t=60, b=40),
    )
    out_html = out_dir / f"{args.out_prefix}_fa_grid.html"
    fig.write_html(out_html, include_plotlyjs="cdn")
    print(f"Wrote {summary_path}")
    print(f"Wrote {out_html}")


if __name__ == "__main__":
    main()
