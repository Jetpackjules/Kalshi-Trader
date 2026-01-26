import argparse
import csv
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_plot_date(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = _parse_date(value)
    if dt:
        return dt
    try:
        return datetime.strptime(value, "%y%b%d")
    except ValueError:
        return None


def _load_daily_equity(out_dir: Path, day_boundary_hour: int) -> list[tuple[datetime, float]]:
    equity_path = out_dir / "equity_history.csv"
    if not equity_path.exists():
        return []
    daily_map: dict[str, float] = {}
    with equity_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = _parse_timestamp(row.get("date", ""))
            if not dt:
                continue
            if day_boundary_hour:
                dt = dt - timedelta(hours=day_boundary_hour)
            key = dt.date().isoformat()
            daily_map[key] = float(row.get("equity") or 0.0)
    daily = []
    for key in sorted(daily_map.keys()):
        daily.append((datetime.fromisoformat(key), daily_map[key]))
    return daily


def _load_tick_equity(out_dir: Path) -> list[tuple[datetime, float]]:
    equity_path = out_dir / "equity_history.csv"
    if not equity_path.exists():
        return []
    ticks = []
    with equity_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = _parse_timestamp(row.get("date", ""))
            if not dt:
                continue
            ticks.append((dt, float(row.get("equity") or 0.0)))
    return ticks


def _load_trade_counts(out_dir: Path, day_boundary_hour: int) -> dict[str, int]:
    trades_path = out_dir / "unified_trades.csv"
    if not trades_path.exists():
        return {}
    counts: dict[str, int] = {}
    with trades_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = _parse_timestamp(row.get("time", ""))
            if not ts:
                continue
            if day_boundary_hour:
                ts = ts - timedelta(hours=day_boundary_hour)
            key = ts.date().isoformat()
            counts[key] = counts.get(key, 0) + 1
    return counts


def _style_for_label(label: str) -> dict:
    mapping = {
        "Best $10": dict(color="#666666", dash="dot", width=2),
        "Current $10": dict(color="#ffb3b3", dash="dot", width=2),
        "Best $100": dict(color="#111111", dash="solid", width=4),
        "Current $100": dict(color="#d62728", dash="solid", width=4),
        "Best $1k": dict(color="#444444", dash="dash", width=3),
        "Current $1k": dict(color="#ff9896", dash="dash", width=3),
        "Best $10k": dict(color="#222222", dash="dashdot", width=3),
        "Current $10k": dict(color="#c0392b", dash="dashdot", width=3),
    }
    return mapping.get(label, {})


def _extract_start_cash(label: str, out_dir: str) -> str | None:
    if "$" in label:
        return label.split("$", 1)[1].strip()
    for token in ("10k", "1k", "1000", "100", "10"):
        if token in label.lower():
            return token
    match = re.search(r"cash(\d+)", out_dir.lower())
    if match:
        value = match.group(1)
        if value.endswith("000"):
            if value == "1000":
                return "1k"
            if value == "10000":
                return "10k"
        return value
    return None


def _roi_series(daily: list[tuple[datetime, float]]) -> list[float]:
    if not daily:
        return []
    base = daily[0][1]
    if base == 0:
        return [0.0 for _ in daily]
    return [((equity / base) - 1.0) * 100.0 for _, equity in daily]


def _daily_returns_from_roi(roi: list[float]) -> list[float]:
    returns = []
    prev = None
    for value in roi:
        if prev is None:
            returns.append(float("nan"))
        else:
            prev_equity = 1.0 + (prev / 100.0)
            curr_equity = 1.0 + (value / 100.0)
            if prev_equity == 0:
                returns.append(float("nan"))
            else:
                returns.append((curr_equity - prev_equity) / prev_equity * 100.0)
        prev = value
    return returns


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate best vs current ROI graph.")
    parser.add_argument("--out-dir", action="append", required=True)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--title", default="Equity (ROI) by Strategy")
    parser.add_argument("--bar-source-label", default="Best $100")
    parser.add_argument(
        "--bar-mode",
        default="returns",
        choices=["returns", "trades", "both"],
        help="What to show in the 2nd subplot: daily returns, trades, or both (adds a 3rd subplot).",
    )
    parser.add_argument(
        "--trade-subplot",
        default="none",
        choices=["none", "label", "all"],
        help="Include a daily trade-count subplot (label or all series).",
    )
    parser.add_argument("--trade-source-label", default="", help="Label to use for trade-count subplot")
    parser.add_argument("--start-date", default="", help="Filter start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="", help="Filter end date (YYYY-MM-DD)")
    parser.add_argument("--max-days", type=int, default=0, help="Limit to N days from start-date (inclusive)")
    parser.add_argument(
        "--day-boundary-hour",
        type=int,
        default=0,
        help="Hour offset for daily boundaries (e.g. 5 means day runs 5am->5am)",
    )
    parser.add_argument(
        "--granularity",
        default="daily",
        choices=["daily", "tick"],
        help="Data granularity to plot",
    )
    parser.add_argument(
        "--baseline-mode",
        default="window",
        choices=["window", "global"],
        help="ROI baseline: window start or full-run start",
    )
    parser.add_argument(
        "--famine-dates",
        default="",
        help="Comma-separated dates to shade (YYYY-MM-DD or 25DEC04).",
    )
    args = parser.parse_args()

    if len(args.out_dir) != len(args.label):
        raise SystemExit("Number of --out-dir and --label args must match.")

    bar_mode = args.bar_mode
    trade_subplot = args.trade_subplot
    if bar_mode == "both":
        trade_subplot = "none"
    rows = 3 if trade_subplot != "none" or bar_mode == "both" else 2
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06 if rows == 3 else 0.08,
    )

    bar_dates = []
    bar_returns = []
    bar_trades = []
    trade_series_to_plot = []

    start_dt = _parse_date(args.start_date)
    end_dt = _parse_date(args.end_date)

    for out_dir_str, label in zip(args.out_dir, args.label):
        if args.granularity == "tick":
            series = _load_tick_equity(Path(out_dir_str))
        else:
            series = _load_daily_equity(Path(out_dir_str), args.day_boundary_hour)
        if not series:
            continue
        global_base = series[0][1]
        if start_dt is None:
            start_dt = series[0][0]
        if args.max_days and args.max_days > 0:
            if args.granularity == "tick":
                end_dt = start_dt + timedelta(days=args.max_days)
            else:
                end_dt = start_dt + timedelta(days=args.max_days - 1)
        if start_dt or end_dt:
            series = [
                item
                for item in series
                if (
                    start_dt is None
                    or (item[0] >= start_dt if args.granularity == "tick" else item[0].date() >= start_dt.date())
                )
                and (
                    end_dt is None
                    or (item[0] < end_dt if args.granularity == "tick" else item[0].date() <= end_dt.date())
                )
            ]
            if not series:
                continue
        dates = [dt for dt, _ in series]
        if args.baseline_mode == "global":
            base = global_base
            roi = [((equity / base) - 1.0) * 100.0 for _, equity in series] if base != 0 else [0.0 for _ in series]
        else:
            roi = _roi_series(series)
        label_parts = []
        start_cash = _extract_start_cash(label, out_dir_str)
        if start_cash:
            label_parts.append(f"start={start_cash}")
        if roi:
            label_parts.append(f"final={roi[-1]:.2f}%")
        label_suffix = ""
        if label_parts:
            label_suffix = f" ({', '.join(label_parts)})"
        display_label = f"{label}{label_suffix}"
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=roi,
                mode="lines",
                name=display_label,
                line=_style_for_label(label),
            ),
            row=1,
            col=1,
        )
        trade_counts = None
        if args.granularity == "daily":
            trade_counts = _load_trade_counts(Path(out_dir_str), args.day_boundary_hour)
            trade_values = [trade_counts.get(dt.date().isoformat(), 0) for dt in dates]
            if label == args.bar_source_label:
                bar_dates = dates
                bar_returns = _daily_returns_from_roi(roi)
                bar_trades = trade_values
        if trade_subplot != "none" and trade_counts is not None:
            trade_values = [trade_counts.get(dt.date().isoformat(), 0) for dt in dates]
            if trade_subplot == "all":
                trade_series_to_plot.append((dates, trade_values, label))
            elif trade_subplot == "label":
                trade_label = args.trade_source_label or args.bar_source_label
                if label == trade_label:
                    trade_series_to_plot.append((dates, trade_values, label))

    if bar_mode == "returns" and bar_dates and bar_returns:
        fig.add_trace(
            go.Bar(
                x=bar_dates,
                y=bar_returns,
                name="Daily Return (%)",
                marker=dict(color="rgba(200, 80, 80, 0.45)"),
                showlegend=False,
            ),
            row=2,
            col=1,
        )
    elif bar_mode == "trades" and bar_dates and bar_trades:
        fig.add_trace(
            go.Bar(
                x=bar_dates,
                y=bar_trades,
                name="Trades",
                marker=dict(color="rgba(90, 120, 200, 0.45)"),
                showlegend=False,
            ),
            row=2,
            col=1,
        )
    elif bar_mode == "both" and bar_dates:
        if bar_trades:
            fig.add_trace(
                go.Bar(
                    x=bar_dates,
                    y=bar_trades,
                    name="Trades",
                    marker=dict(color="rgba(90, 120, 200, 0.45)"),
                    showlegend=False,
                ),
                row=2,
                col=1,
            )
        if bar_returns:
            fig.add_trace(
                go.Bar(
                    x=bar_dates,
                    y=bar_returns,
                    name="Daily Return (%)",
                    marker=dict(color="rgba(200, 80, 80, 0.45)"),
                    showlegend=False,
                ),
                row=3,
                col=1,
            )

    if trade_series_to_plot and rows == 3 and bar_mode != "both":
        for dates, values, label in trade_series_to_plot:
            if trade_subplot == "all":
                fig.add_trace(
                    go.Scatter(
                        x=dates,
                        y=values,
                        mode="lines",
                        name=f"Trades {label}",
                        line=dict(width=1, dash="dot"),
                        showlegend=True,
                    ),
                    row=3,
                    col=1,
                )
            else:
                fig.add_trace(
                    go.Bar(
                        x=dates,
                        y=values,
                        name="Trades",
                        marker=dict(color="rgba(90, 120, 200, 0.45)"),
                        showlegend=False,
                    ),
                    row=3,
                    col=1,
                )

    if args.famine_dates:
        for token in [t.strip() for t in args.famine_dates.split(",") if t.strip()]:
            dt = _parse_plot_date(token)
            if not dt:
                continue
            x0 = dt
            x1 = dt + timedelta(days=1)
            fig.add_shape(
                type="rect",
                xref="x",
                yref="paper",
                x0=x0,
                x1=x1,
                y0=0.0,
                y1=1.0,
                fillcolor="rgba(220, 20, 60, 0.12)",
                line=dict(width=0),
                layer="below",
                row=1,
                col=1,
            )

    fig.update_layout(
        hovermode="x unified",
        height=900 if rows == 3 else 720,
        legend=dict(orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.02),
        margin=dict(l=60, r=220, t=80, b=60),
        annotations=[
            dict(
                text=args.title,
                x=0.5,
                xref="paper",
                xanchor="center",
                y=1.0,
                yref="paper",
                yanchor="bottom",
                showarrow=False,
                font=dict(size=16),
            ),
            dict(
                text="Daily Trades" if bar_mode in ("trades", "both") else "Daily Return (%)",
                x=0.5,
                xref="paper",
                xanchor="center",
                y=0.276 if rows == 2 else 0.38,
                yref="paper",
                yanchor="bottom",
                showarrow=False,
                font=dict(size=16),
            ),
            *(
                [
                    dict(
                        text="Daily Return (%)" if bar_mode == "both" else "Daily Trades",
                        x=0.5,
                        xref="paper",
                        xanchor="center",
                        y=0.12,
                        yref="paper",
                        yanchor="bottom",
                        showarrow=False,
                        font=dict(size=16),
                    )
                ]
                if rows == 3
                else []
            ),
        ],
    )
    if args.granularity == "daily":
        fig.update_xaxes(showticklabels=False, row=1, col=1)
        if rows == 3:
            fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_yaxes(title_text="ROI (%)", row=1, col=1)
    if args.granularity == "daily":
        fig.update_yaxes(title_text="Daily Return (%)", row=2, col=1)
        if rows == 3:
            fig.update_xaxes(title_text="Date", row=3, col=1)
            fig.update_yaxes(title_text="Trades", row=3, col=1)
        else:
            fig.update_xaxes(title_text="Date", row=2, col=1)
    else:
        fig.update_xaxes(title_text="Time", row=1, col=1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_path)
    print(f"Wrote ROI comparison chart: {out_path}")


if __name__ == "__main__":
    main()
