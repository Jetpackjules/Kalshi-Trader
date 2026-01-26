import argparse
import csv
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, time
from pathlib import Path

import plotly.graph_objects as go


def _parse_date(value: str) -> datetime.date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _date_range(start_date: datetime.date, end_date: datetime.date) -> list[datetime.date]:
    days = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def _start_ts_for_day(day: datetime.date, day_boundary_hour: int) -> datetime:
    return datetime.combine(day, time(hour=day_boundary_hour))


def _read_last_equity(out_dir: Path) -> tuple[datetime, float] | None:
    path = out_dir / "equity_history.csv"
    if not path.exists():
        return None
    last_row = None
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            last_row = row
    if not last_row:
        return None
    try:
        end_ts = datetime.fromisoformat(last_row["date"])
    except (ValueError, KeyError):
        return None
    try:
        equity = float(last_row["equity"])
    except (ValueError, KeyError):
        return None
    return end_ts, equity


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rolling-start backtests and compute avg ROI/day.")
    parser.add_argument("--start-date", default="2025-12-04", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="", help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--snapshot", default="dec05_snapshot.json", help="Snapshot path")
    parser.add_argument("--strategy", default="recommended_live_strategy_dec100", help="Strategy name")
    parser.add_argument("--strategy-kwargs", default="", help="JSON string of strategy kwargs")
    parser.add_argument("--initial-cash", type=float, default=100.0, help="Initial cash per run")
    parser.add_argument("--warmup-hours", type=int, default=0, help="Warmup hours before start")
    parser.add_argument(
        "--min-requote-interval",
        type=float,
        default=0.0,
        help="Minimum interval between order recalcs (seconds)",
    )
    parser.add_argument(
        "--day-boundary-hour",
        type=int,
        default=0,
        help="Hour offset for daily boundaries (e.g. 5 means day runs 5am->5am)",
    )
    parser.add_argument("--famine-days", type=int, default=0, help="Consecutive losing days before pausing trading")
    parser.add_argument("--abundance-days", type=int, default=0, help="Consecutive winning days before resuming")
    parser.add_argument("--famine-daily-pct", type=float, default=0.0, help="Daily pct <= threshold counts as famine")
    parser.add_argument("--abundance-daily-pct", type=float, default=0.0, help="Daily pct >= threshold counts as abundance")
    parser.add_argument(
        "--resume-restart-mode",
        type=str,
        default="off",
        choices=["off", "intraday", "eod"],
        help="Resume from famine using a shadow restart sim",
    )
    parser.add_argument(
        "--resume-restart-pct",
        type=float,
        default=0.0,
        help="Restart ROI threshold (%) required to resume",
    )
    parser.add_argument(
        "--out-prefix",
        default="unified_engine_comparison/rolling_start_dec04_dec100_",
        help="Output dir prefix",
    )
    parser.add_argument("--out-csv", default="backtest_charts/rolling_start_roi.csv", help="Output CSV path")
    parser.add_argument("--out-html", default="backtest_charts/rolling_start_roi.html", help="Output HTML path")
    parser.add_argument("--skip-existing", action="store_true", help="Skip runs with existing equity_history.csv")
    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, os.cpu_count() or 4),
        help="Max parallel workers",
    )
    args = parser.parse_args()

    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date) if args.end_date else datetime.now().date()
    days = _date_range(start_date, end_date)
    total = len(days)
    if total == 0:
        raise SystemExit("No dates to process.")

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    results = []
    pending_days = []
    for idx, day in enumerate(days, start=1):
        start_ts = _start_ts_for_day(day, args.day_boundary_hour)
        start_ts_str = start_ts.strftime("%Y-%m-%d %H:%M:%S")
        out_dir = Path(f"{args.out_prefix}{day.strftime('%Y%m%d')}")
        equity_path = out_dir / "equity_history.csv"
        if args.skip_existing and equity_path.exists():
            pct = (idx / total) * 100.0
            print(f"[{idx}/{total} | {pct:5.1f}%] Skip {day.isoformat()} (exists)")
            last = _read_last_equity(out_dir)
            if last:
                end_ts, final_equity = last
                elapsed_days = max((end_ts - start_ts).total_seconds() / 86400.0, 1e-9)
                roi_pct = (final_equity / args.initial_cash - 1.0) * 100.0
                avg_roi_per_day = roi_pct / elapsed_days
                results.append(
                    {
                        "start_date": day.isoformat(),
                        "start_ts": start_ts.isoformat(sep=" "),
                        "end_ts": end_ts.isoformat(sep=" "),
                        "days": f"{elapsed_days:.4f}",
                        "final_equity": f"{final_equity:.4f}",
                        "roi_pct": f"{roi_pct:.4f}",
                        "avg_roi_per_day_pct": f"{avg_roi_per_day:.4f}",
                        "out_dir": str(out_dir),
                    }
                )
            continue
        pending_days.append((day, start_ts_str, out_dir))

    def _run_day(day: datetime.date, start_ts_str: str, out_dir: Path) -> datetime.date:
        cmd = [
            sys.executable,
            "run_unified_backtest.py",
            "--snapshot",
            args.snapshot,
            "--start-ts",
            start_ts_str,
            "--initial-cash",
            f"{args.initial_cash}",
            "--strategy",
            args.strategy,
            "--out-dir",
            str(out_dir),
            "--warmup-hours",
            str(args.warmup_hours),
            "--min-requote-interval",
            str(args.min_requote_interval),
            "--day-boundary-hour",
            str(args.day_boundary_hour),
            "--quiet",
        ]
        if args.strategy_kwargs and args.strategy_kwargs != "{}":
            cmd.extend(["--strategy-kwargs", args.strategy_kwargs])
        if args.famine_days and args.abundance_days:
            cmd.extend(
                [
                    "--famine-days",
                    str(args.famine_days),
                    "--abundance-days",
                    str(args.abundance_days),
                    "--famine-daily-pct",
                    str(args.famine_daily_pct),
                    "--abundance-daily-pct",
                    str(args.abundance_daily_pct),
                ]
            )
        if args.resume_restart_mode != "off":
            cmd.extend(["--resume-restart-mode", args.resume_restart_mode])
            if args.resume_restart_pct:
                cmd.extend(["--resume-restart-pct", str(args.resume_restart_pct)])
        subprocess.run(cmd, check=True)
        return day

    if pending_days:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {}
            for idx, (day, start_ts_str, out_dir) in enumerate(pending_days, start=1):
                pct = (idx / len(pending_days)) * 100.0
                print(f"[{idx}/{len(pending_days)} | {pct:5.1f}%] start={start_ts_str}")
                futures[executor.submit(_run_day, day, start_ts_str, out_dir)] = day
            for future in as_completed(futures):
                day = futures[future]
                try:
                    future.result()
                except subprocess.CalledProcessError as exc:
                    print(f"ERROR {day.isoformat()} (exit={exc.returncode})")

    for idx, day in enumerate(days, start=1):
        start_ts = _start_ts_for_day(day, args.day_boundary_hour)
        out_dir = Path(f"{args.out_prefix}{day.strftime('%Y%m%d')}")
        last = _read_last_equity(out_dir)
        if not last:
            print(f"[{idx}/{total}] Missing equity history for {day.isoformat()}")
            continue
        end_ts, final_equity = last
        elapsed_days = max((end_ts - start_ts).total_seconds() / 86400.0, 1e-9)
        roi_pct = (final_equity / args.initial_cash - 1.0) * 100.0
        avg_roi_per_day = roi_pct / elapsed_days
        results.append(
            {
                "start_date": day.isoformat(),
                "start_ts": start_ts.isoformat(sep=" "),
                "end_ts": end_ts.isoformat(sep=" "),
                "days": f"{elapsed_days:.4f}",
                "final_equity": f"{final_equity:.4f}",
                "roi_pct": f"{roi_pct:.4f}",
                "avg_roi_per_day_pct": f"{avg_roi_per_day:.4f}",
                "out_dir": str(out_dir),
            }
        )

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "start_date",
            "start_ts",
            "end_ts",
            "days",
            "final_equity",
            "roi_pct",
            "avg_roi_per_day_pct",
            "out_dir",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"Wrote {out_csv}")

    if results:
        dates = [r["start_date"] for r in results]
        avg_vals = [float(r["avg_roi_per_day_pct"]) for r in results]
        roi_vals = [float(r["roi_pct"]) for r in results]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=avg_vals,
                mode="lines+markers",
                name="Avg ROI/day (%)",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=roi_vals,
                mode="lines",
                name="Total ROI (%)",
                yaxis="y2",
                line=dict(dash="dot"),
            )
        )
        fig.update_layout(
            title="Rolling Start ROI (Avg per Day)",
            xaxis=dict(title="Start date"),
            yaxis=dict(title="Avg ROI/day (%)"),
            yaxis2=dict(title="Total ROI (%)", overlaying="y", side="right"),
            legend=dict(orientation="h"),
            margin=dict(l=40, r=40, t=60, b=40),
        )
        out_html = Path(args.out_html)
        out_html.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(out_html, include_plotlyjs="cdn")
        print(f"Wrote {out_html}")


if __name__ == "__main__":
    main()
