from __future__ import annotations

from backtesting.engine import RegimeSwitcher


def meta_regime_switcher_default() -> RegimeSwitcher:
    # Matches the ComplexBacktester() default strategy (no kwargs).
    return RegimeSwitcher("Algo 3: Regime Switcher (Meta)")


def meta_regime_switcher_uncapped() -> RegimeSwitcher:
    return RegimeSwitcher("meta_uncapped", max_inventory=None)


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


# --- High-budget sweep variants ---


def hb_base() -> RegimeSwitcher:
    return RegimeSwitcher(
        "hb_base",
        risk_pct=0.8,
        tightness_percentile=20,
        max_inventory=80,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.08,
        max_loss_pct=0.03,
    )


def hb_risk_060() -> RegimeSwitcher:
    return RegimeSwitcher(
        "hb_risk_060",
        risk_pct=0.6,
        tightness_percentile=20,
        max_inventory=80,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.08,
        max_loss_pct=0.03,
    )


def hb_risk_090() -> RegimeSwitcher:
    return RegimeSwitcher(
        "hb_risk_090",
        risk_pct=0.9,
        tightness_percentile=20,
        max_inventory=80,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.08,
        max_loss_pct=0.03,
    )


def hb_notional_010() -> RegimeSwitcher:
    # Allow larger position sizing per opportunity.
    return RegimeSwitcher(
        "hb_notional_010",
        risk_pct=0.8,
        tightness_percentile=20,
        max_inventory=100,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


def hb_notional_010_risk_020() -> RegimeSwitcher:
    return RegimeSwitcher(
        "hb_notional_010_risk_020",
        risk_pct=0.20,
        tightness_percentile=20,
        max_inventory=100,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


def hb_notional_010_risk_040() -> RegimeSwitcher:
    return RegimeSwitcher(
        "hb_notional_010_risk_040",
        risk_pct=0.40,
        tightness_percentile=20,
        max_inventory=100,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


def hb_notional_010_risk_060() -> RegimeSwitcher:
    return RegimeSwitcher(
        "hb_notional_010_risk_060",
        risk_pct=0.60,
        tightness_percentile=20,
        max_inventory=100,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


def hb_notional_010_risk_080() -> RegimeSwitcher:
    return RegimeSwitcher(
        "hb_notional_010_risk_080",
        risk_pct=0.80,
        tightness_percentile=20,
        max_inventory=100,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


def hb_notional_010_risk_100() -> RegimeSwitcher:
    return RegimeSwitcher(
        "hb_notional_010_risk_100",
        risk_pct=1.00,
        tightness_percentile=20,
        max_inventory=100,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


def hb_notional_010_uncapped() -> RegimeSwitcher:
    return RegimeSwitcher(
        "hb_notional_010_uncapped",
        risk_pct=0.8,
        tightness_percentile=20,
        max_inventory=None,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


def hb_loss_040() -> RegimeSwitcher:
    # Allow more risk per day (and therefore more size).
    return RegimeSwitcher(
        "hb_loss_040",
        risk_pct=0.8,
        tightness_percentile=20,
        max_inventory=100,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.08,
        max_loss_pct=0.04,
    )


def hb_tight_30() -> RegimeSwitcher:
    # Trade slightly more often (less strict spread gate).
    return RegimeSwitcher(
        "hb_tight_30",
        risk_pct=0.8,
        tightness_percentile=30,
        max_inventory=80,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.08,
        max_loss_pct=0.03,
    )


def hb_tight_10() -> RegimeSwitcher:
    # More selective on spread.
    return RegimeSwitcher(
        "hb_tight_10",
        risk_pct=0.8,
        tightness_percentile=10,
        max_inventory=80,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.08,
        max_loss_pct=0.03,
    )


def hb_margin_030() -> RegimeSwitcher:
    # Require a bit less edge beyond fees.
    return RegimeSwitcher(
        "hb_margin_030",
        risk_pct=0.8,
        tightness_percentile=20,
        max_inventory=80,
        margin_cents=3.0,
        scaling_factor=4.0,
        max_notional_pct=0.08,
        max_loss_pct=0.03,
    )


def hb_margin_050() -> RegimeSwitcher:
    # Require more edge beyond fees.
    return RegimeSwitcher(
        "hb_margin_050",
        risk_pct=0.8,
        tightness_percentile=20,
        max_inventory=80,
        margin_cents=5.0,
        scaling_factor=4.0,
        max_notional_pct=0.08,
        max_loss_pct=0.03,
    )


def hb_scaling_060() -> RegimeSwitcher:
    # Slower size ramp-up vs edge.
    return RegimeSwitcher(
        "hb_scaling_060",
        risk_pct=0.8,
        tightness_percentile=20,
        max_inventory=80,
        margin_cents=4.0,
        scaling_factor=6.0,
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
