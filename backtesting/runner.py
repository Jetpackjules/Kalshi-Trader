from __future__ import annotations

import argparse
import importlib
import inspect
import json
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

from backtesting.engine import ComplexBacktester


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


def _parse_snapshot_timestamp(data: dict) -> datetime:
    ts_str = data.get("timestamp") or data.get("last_update")
    if not ts_str:
        raise ValueError("Snapshot missing 'timestamp'/'last_update'")
    return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")


def _dt_to_datestr(dt: datetime) -> str:
    return dt.strftime("%y%b%d").upper()


def _seed_portfolio_from_snapshot(bt: ComplexBacktester, strategy_name: str, snapshot: dict) -> float:
    p = bt.portfolios[strategy_name]

    daily_start_equity = float(snapshot.get("daily_start_equity") or 0.0)
    balance = float(snapshot.get("balance") or snapshot.get("cash") or 0.0)
    base_capital = daily_start_equity if daily_start_equity > 0 else balance

    p["wallet"].available_cash = balance
    p["wallet"].unsettled_positions = []
    p["daily_start_equity"] = base_capital

    positions = snapshot.get("positions") or {}
    for ticker, pos in positions.items():
        yes_qty = int(pos.get("yes") or 0)
        no_qty = int(pos.get("no") or 0)
        cost = float(pos.get("cost") or 0.0)

        if yes_qty > 0:
            p["inventory_yes"]["MM"][ticker] = yes_qty
        if no_qty > 0:
            p["inventory_no"]["MM"][ticker] = no_qty
        if cost > 0:
            p["cost_basis"][ticker] = cost

    # Keep reporting consistent with the seeded budget basis.
    bt.initial_capital = base_capital
    return base_capital


def _load_strategy_factory(spec: StrategySpec) -> Callable[[], object]:
    mod = importlib.import_module(spec.module)
    sym = getattr(mod, spec.symbol)
    if callable(sym):
        return sym
    raise TypeError(f"{spec.module}:{spec.symbol} is not callable")


def _call_strategy_factory(factory: Callable[..., object], *, initial_capital: float) -> object:
    sig = inspect.signature(factory)
    params = sig.parameters

    if not params:
        return factory()

    kwargs: dict[str, object] = {}
    if "initial_capital" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        kwargs["initial_capital"] = initial_capital
    return factory(**kwargs)


def _set_max_inventory(strategy: object, max_inventory: int | None) -> None:
    # RegimeSwitcher-style wrapper
    if hasattr(strategy, "mm") and hasattr(getattr(strategy, "mm"), "max_inventory"):
        getattr(strategy, "mm").max_inventory = max_inventory

    # Direct MM-style strategy
    if hasattr(strategy, "max_inventory"):
        setattr(strategy, "max_inventory", max_inventory)


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
    parser.add_argument("--snapshot", default="", help="Optional snapshot JSON path to seed starting state")
    parser.add_argument(
        "--end-ts",
        default="",
        help="Optional end timestamp (YYYY-mm-dd HH:MM:SS). Useful with --snapshot for intraday replays.",
    )
    parser.add_argument(
        "--simulate-live",
        action="store_true",
        help="Best-effort live parity: round prices to int, seed warmup from pre-start ticks, and apply a per-ticker requote throttle.",
    )
    parser.add_argument(
        "--buy-slippage-cents",
        type=float,
        default=0.0,
        help="Hypothetical buy-side slippage (in cents) applied to BUY_YES/BUY_NO execution prices.",
    )
    parser.add_argument(
        "--min-requote-interval",
        type=float,
        default=2.0,
        help="Used with --simulate-live. Minimum seconds between strategy evaluations per ticker.",
    )
    parser.add_argument("--initial-capital", type=float, default=1000.0)
    parser.add_argument(
        "--max-inventory",
        type=int,
        default=None,
        help="Override max inventory cap (contracts). If omitted, use strategy default or --inventory-per-dollar.",
    )
    parser.add_argument(
        "--inventory-per-dollar",
        type=float,
        default=None,
        help="Set max inventory as round(initial_capital * K). Example: if $100 used 50, K=0.5.",
    )
    parser.add_argument("--log-dir", default="", help="Market logs dir; defaults to vm_logs/server_mirror autodetect")
    parser.add_argument("--charts-dir", default="backtest_charts")
    parser.add_argument(
        "--out",
        default=os.path.join("backtest_charts", "comparison_variants.html"),
        help="Output HTML path",
    )

    args = parser.parse_args()

    if not args.strategy:
        # Keep CLI friction low while staying within the modular strategy system.
        args.strategy = ["backtesting.strategies.v3_variants:meta_regime_switcher_default"]

    log_dir = args.log_dir.strip() or _pick_log_dir()
    charts_dir = args.charts_dir
    os.makedirs(charts_dir, exist_ok=True)

    snapshot = None
    snapshot_start_dt: datetime | None = None
    snapshot_end_dt: datetime | None = None
    base_capital = float(args.initial_capital)

    if args.snapshot.strip():
        with open(args.snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        snapshot_start_dt = _parse_snapshot_timestamp(snapshot)
        base_capital = float(snapshot.get("daily_start_equity") or 0.0) or float(snapshot.get("balance") or snapshot.get("cash") or base_capital)
        if args.end_ts:
            snapshot_end_dt = datetime.strptime(args.end_ts, "%Y-%m-%d %H:%M:%S")

    specs = _parse_strategy_specs(args.strategy)
    strategies = []
    for spec in specs:
        factory = _load_strategy_factory(spec)
        strat = _call_strategy_factory(factory, initial_capital=base_capital)

        if args.max_inventory is not None:
            _set_max_inventory(strat, args.max_inventory)
        elif args.inventory_per_dollar is not None:
            scaled = int(round(args.initial_capital * args.inventory_per_dollar))
            _set_max_inventory(strat, scaled)

        # Best-effort: apply snapshot strategy config (if present) unless user overrides via flags.
        if snapshot is not None:
            cfg = snapshot.get("strategy_config") or {}
            if args.max_inventory is None and args.inventory_per_dollar is None and "max_inventory" in cfg:
                _set_max_inventory(strat, cfg.get("max_inventory"))
            if hasattr(strat, "risk_pct") and "risk_pct" in cfg:
                setattr(strat, "risk_pct", float(cfg["risk_pct"]))
            if hasattr(strat, "tightness_percentile") and "tightness_percentile" in cfg:
                setattr(strat, "tightness_percentile", int(cfg["tightness_percentile"]))

        strategies.append(strat)

    start_date = args.start_date
    end_date = args.end_date
    if snapshot_start_dt is not None:
        start_date = _dt_to_datestr(snapshot_start_dt)
        # If the user didn't provide an end-date, keep it open.

    bt = ComplexBacktester(
        strategies=strategies,
        log_dir=log_dir,
        charts_dir=charts_dir,
        start_date=start_date,
        end_date=end_date,
        start_datetime=snapshot_start_dt,
        end_datetime=snapshot_end_dt,
        buy_slippage_cents=float(args.buy_slippage_cents or 0.0),
        seed_warmup_from_history=bool(args.simulate_live),
        round_prices_to_int=bool(args.simulate_live),
        min_requote_interval_seconds=(float(args.min_requote_interval) if args.simulate_live else 0.0),
        initial_capital=base_capital,
        generate_daily_charts=False,
        generate_final_chart=False,
    )

    if snapshot is not None:
        for s in strategies:
            _seed_portfolio_from_snapshot(bt, s.name, snapshot)

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
