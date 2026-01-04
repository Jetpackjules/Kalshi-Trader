from __future__ import annotations

import argparse
import importlib
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

import plotly.graph_objects as go
from plotly.subplots import make_subplots


# Allow running as `python backtesting/runner.py` from the repo root.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from complex_strategy_backtest import ComplexBacktester


LOG_DIR_CANDIDATES = [
    os.path.join(os.getcwd(), "vm_logs", "market_logs"),
    os.path.join(os.getcwd(), "server_mirror", "market_logs"),
    os.path.join(os.getcwd(), "live_trading_system", "vm_logs", "market_logs"),
]


@dataclass(frozen=True)
class StrategySpec:
    module: str
    symbol: str


def _pick_log_dir() -> str:
    return next((d for d in LOG_DIR_CANDIDATES if os.path.exists(d)), LOG_DIR_CANDIDATES[0])


def _load_strategy_factory(spec: StrategySpec) -> Callable[[], object]:
    mod = importlib.import_module(spec.module)
    sym = getattr(mod, spec.symbol)
    if callable(sym):
        return sym
    raise TypeError(f"{spec.module}:{spec.symbol} is not callable")


def _parse_strategy_specs(raw: Iterable[str]) -> list[StrategySpec]:
    specs: list[StrategySpec] = []
    for item in raw:
        if ":" not in item:
            raise ValueError(f"Invalid --strategy '{item}'. Use module:symbol")
        module, symbol = item.split(":", 1)
        specs.append(StrategySpec(module=module.strip(), symbol=symbol.strip()))
    if not specs:
        raise ValueError("At least one --strategy is required")
    return specs


def _equity_history_to_series(history: list[dict]) -> tuple[list[str], list[float]]:
    dates = [h["date"] for h in history]
    equities = [float(h["equity"]) for h in history]
    return dates, equities


def _series_to_daily_returns(equities: list[float]) -> list[float]:
    out: list[float] = []
    prev = None
    for e in equities:
        if prev is None or prev == 0:
            out.append(0.0)
        else:
            out.append((e - prev) / prev)
        prev = e
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run modular backtests and compare variants on one graph.")
    parser.add_argument(
        "--strategy",
        action="append",
        default=[],
        help="Strategy factory in module:symbol form. Repeatable.",
    )
    parser.add_argument("--start-date", default="25DEC04", help="YYMONDD, e.g. 25DEC04")
    parser.add_argument("--end-date", default="", help="YYMONDD, empty means no upper bound")
    parser.add_argument("--initial-capital", type=float, default=1000.0)
    parser.add_argument("--log-dir", default="", help="Market logs dir; defaults to vm_logs/server_mirror autodetect")
    parser.add_argument("--charts-dir", default="backtest_charts")
    parser.add_argument(
        "--out",
        default=os.path.join("backtest_charts", "comparison_variants.html"),
        help="Output HTML path",
    )

    args = parser.parse_args()

    log_dir = args.log_dir.strip() or _pick_log_dir()
    charts_dir = args.charts_dir
    os.makedirs(charts_dir, exist_ok=True)

    specs = _parse_strategy_specs(args.strategy)
    strategies = []
    for spec in specs:
        factory = _load_strategy_factory(spec)
        strategies.append(factory())

    bt = ComplexBacktester(
        strategies=strategies,
        log_dir=log_dir,
        charts_dir=charts_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.initial_capital,
        generate_daily_charts=False,
        generate_final_chart=False,
    )

    started = datetime.now()
    bt.run()
    elapsed = datetime.now() - started

    if not hasattr(bt, "daily_equity_history"):
        raise RuntimeError("No daily_equity_history produced (no data or date range mismatch)")

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Equity (MTM) by Strategy", "Daily Return (%)"),
    )

    for strat_name, history in bt.daily_equity_history.items():
        dates, equities = _equity_history_to_series(history)
        daily_rets = [r * 100.0 for r in _series_to_daily_returns(equities)]

        fig.add_trace(
            go.Scatter(x=dates, y=equities, mode="lines+markers", name=strat_name),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Bar(x=dates, y=daily_rets, name=f"{strat_name} daily %", opacity=0.35, showlegend=False),
            row=2,
            col=1,
        )

    fig.update_layout(
        title=f"Variant Comparison (elapsed {elapsed})",
        hovermode="x unified",
        height=900,
    )
    fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
    fig.update_yaxes(title_text="Daily Return (%)", row=2, col=1)

    fig.write_html(args.out)
    print(f"Wrote comparison chart: {args.out}")
    print(f"Used log_dir: {log_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
