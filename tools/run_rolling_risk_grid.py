import argparse
import csv
import json
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
            try:
                values.append(float(val))
                dates.append(date)
            except ValueError:
                continue
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


def _positive_rate(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if v > 0) / len(values)


def _parse_float_list(value: str) -> list[float]:
    return [float(v.strip()) for v in value.split(",") if v.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rolling-start grid for risk/notional caps.")
    parser.add_argument("--start-date", default="2025-12-04", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2026-01-13", help="End date (YYYY-MM-DD)")
    parser.add_argument("--snapshot", default="dec05_snapshot.json", help="Snapshot path")
    parser.add_argument("--initial-cash", type=float, default=100.0, help="Initial cash per run")
    parser.add_argument("--warmup-hours", type=int, default=0, help="Warmup hours")
    parser.add_argument("--min-requote-interval", type=float, default=0.0, help="Min requote interval (seconds)")
    parser.add_argument("--day-boundary-hour", type=int, default=5, help="Day boundary hour")
    parser.add_argument("--famine-days", type=int, default=2, help="Consecutive losing days before pausing")
    parser.add_argument("--abundance-days", type=int, default=2, help="Consecutive winning days before resuming")
    parser.add_argument("--famine-daily-pct", type=float, default=0.0, help="Daily pct <= threshold counts as famine")
    parser.add_argument("--abundance-daily-pct", type=float, default=0.0, help="Daily pct >= threshold counts as abundance")
    parser.add_argument("--risk-pcts", default="0.4,0.6,0.8,1.0", help="Comma-separated risk_pct values")
    parser.add_argument("--notional-pcts", default="0.05,0.08,0.10,0.15", help="Comma-separated max_notional_pct values")
    parser.add_argument("--decision-cash", type=float, default=100.0, help="Decision budget cash")
    parser.add_argument("--workers", type=int, default=32, help="Workers per rolling run")
    parser.add_argument("--out-dir", default="backtest_charts", help="Output directory")
    parser.add_argument("--out-prefix", default="rolling_start_roi_dec04_dec100_risk_grid", help="Output prefix")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    risk_pcts = _parse_float_list(args.risk_pcts)
    notional_pcts = _parse_float_list(args.notional_pcts)

    summary_rows = []
    csv_paths = []
    for risk_pct in risk_pcts:
        for max_notional_pct in notional_pcts:
            label = f"r{int(risk_pct * 100)}_n{int(max_notional_pct * 100)}"
            out_csv = out_dir / f"{args.out_prefix}_{label}_5am.csv"
            out_html = out_dir / f"{args.out_prefix}_{label}_5am.html"
            out_prefix = f"unified_engine_comparison/{args.out_prefix}_{label}_5am_"

            strategy_kwargs = {
                "name": f"{args.out_prefix}_{label}",
                "risk_pct": risk_pct,
                "tightness_percentile": 10,
                "max_inventory": 150,
                "margin_cents": 8.0,
                "scaling_factor": 2.0,
                "max_notional_pct": max_notional_pct,
                "max_loss_pct": 0.03,
                "decision_budget_cash": args.decision_cash,
            }

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
                "generic_v3",
                "--strategy-kwargs",
                json.dumps(strategy_kwargs),
                "--initial-cash",
                str(args.initial_cash),
                "--warmup-hours",
                str(args.warmup_hours),
                "--min-requote-interval",
                str(args.min_requote_interval),
                "--day-boundary-hour",
                str(args.day_boundary_hour),
                "--famine-days",
                str(args.famine_days),
                "--abundance-days",
                str(args.abundance_days),
                "--famine-daily-pct",
                str(args.famine_daily_pct),
                "--abundance-daily-pct",
                str(args.abundance_daily_pct),
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
            subprocess.run(cmd, check=True)

            series = _read_avg_series(out_csv)
            if not series:
                continue
            _, values = series
            summary_rows.append(
                {
                    "combo": label,
                    "risk_pct": f"{risk_pct:.2f}",
                    "max_notional_pct": f"{max_notional_pct:.2f}",
                    "mean_avg_roi_per_day_pct": f"{_mean(values):.4f}",
                    "median_avg_roi_per_day_pct": f"{_median(values):.4f}",
                    "positive_rate": f"{_positive_rate(values):.4f}",
                }
            )
            csv_paths.append((label, out_csv))

    summary_path = out_dir / f"{args.out_prefix}_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "combo",
                "risk_pct",
                "max_notional_pct",
                "mean_avg_roi_per_day_pct",
                "median_avg_roi_per_day_pct",
                "positive_rate",
            ],
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
        title="Rolling Start ROI (Avg per Day) - Risk/Notional Grid",
        xaxis=dict(title="Start date"),
        yaxis=dict(title="Avg ROI/day (%)"),
        legend=dict(orientation="h"),
        margin=dict(l=40, r=40, t=60, b=40),
    )
    out_html = out_dir / f"{args.out_prefix}.html"
    fig.write_html(out_html, include_plotlyjs="cdn")
    print(f"Wrote {summary_path}")
    print(f"Wrote {out_html}")


if __name__ == "__main__":
    main()
