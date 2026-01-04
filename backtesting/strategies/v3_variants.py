from __future__ import annotations

from complex_strategy_backtest import RegimeSwitcher


def baseline_v3() -> RegimeSwitcher:
    # Mirrors current backtester defaults (v3-style)
    return RegimeSwitcher(
        "v3_baseline",
        risk_pct=0.5,
        tightness_percentile=20,
        max_inventory=50,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.05,
        max_loss_pct=0.02,
    )


def looser_gates_more_trades() -> RegimeSwitcher:
    # Trades more often: accepts wider spreads and requires less edge after fees.
    return RegimeSwitcher(
        "v3_looser_gates",
        risk_pct=0.5,
        tightness_percentile=45,
        max_inventory=50,
        margin_cents=2.0,
        scaling_factor=4.0,
        max_notional_pct=0.05,
        max_loss_pct=0.02,
    )


def tighter_gates_fewer_trades() -> RegimeSwitcher:
    # More selective: tighter spread requirement + higher edge margin.
    return RegimeSwitcher(
        "v3_tighter_gates",
        risk_pct=0.5,
        tightness_percentile=10,
        max_inventory=50,
        margin_cents=6.0,
        scaling_factor=4.0,
        max_notional_pct=0.05,
        max_loss_pct=0.02,
    )


def higher_budget_same_edges() -> RegimeSwitcher:
    # Same signal quality, but allow larger notional and daily risk budget.
    return RegimeSwitcher(
        "v3_higher_budget",
        risk_pct=0.8,
        tightness_percentile=20,
        max_inventory=80,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.08,
        max_loss_pct=0.03,
    )


def conservative_sizing() -> RegimeSwitcher:
    # Similar entries, smaller sizing caps.
    return RegimeSwitcher(
        "v3_conservative_size",
        risk_pct=0.4,
        tightness_percentile=20,
        max_inventory=35,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.03,
        max_loss_pct=0.015,
    )
