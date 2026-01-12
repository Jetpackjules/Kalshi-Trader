from __future__ import annotations

from server_mirror.backtesting.engine import RegimeSwitcher


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


def sniper_v3() -> RegimeSwitcher:
    # "The Sniper": Only trades when spreads are extremely tight (top 5 percentile).
    # Avoids wide markets completely.
    return RegimeSwitcher(
        "v3_sniper",
        risk_pct=0.8,
        tightness_percentile=5,  # Only trade if spread is in the tightest 5% of history
        max_inventory=100,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


def bargain_hunter_v3(margin_cents=10.0) -> RegimeSwitcher:
    # "The Bargain Hunter": Demands a massive edge (10 cents) to enter.
    # If spread is 5c, we need >15c edge. Ensures we never pay for bad odds.
    return RegimeSwitcher(
        f"v3_bargain_hunter_m{margin_cents}",
        risk_pct=0.8,
        tightness_percentile=50, # Looser gate, but...
        max_inventory=100,
        margin_cents=margin_cents,       # ...Huge margin requirement
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


def closer_v3() -> RegimeSwitcher:
    # "The Closer": Standard logic, but relies on external time constraints 
    # (e.g., run with --active-hours 22,23) to only trade near expiry.
    # We use tighter gates here to ensure we don't get run over at the close.
    return RegimeSwitcher(
        "v3_closer",
        risk_pct=0.8,
        active_hours=[21, 22, 23], # Enforce late-night trading only
        tightness_percentile=15,
        max_inventory=100,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )


class HybridRegimeSwitcher(RegimeSwitcher):
    """
    Adapts behavior based on market width:
    - Tight Market (< 5c): Be Aggressive (Low Margin, High Activity)
    - Wide Market (> 5c): Be Passive (High Margin, "Bargain Hunter")
    """
    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        # 1. Calculate Spread
        yes_ask = market_state.get('yes_ask')
        yes_bid = market_state.get('yes_bid')
        if yes_ask is None or yes_bid is None: return None
        spread = yes_ask - yes_bid
        
        # 2. Dynamic Parameter Adjustment
        if spread <= 5:
            # Tight Market -> Baseline Mode
            self.mm.margin_cents = 4.0
            self.tightness_percentile = 20 # Standard gating
        else:
            # Wide Market -> Bargain Hunter Mode
            self.mm.margin_cents = 10.0
            self.tightness_percentile = 50 # Looser gate (allow wide) but high margin
            
        # 3. Delegate to Parent
        return super().on_market_update(ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx)


def hybrid_v3() -> RegimeSwitcher:
    # "The Hybrid": Best of both worlds.
    # Uses a custom class that switches logic dynamically.
    strategy = HybridRegimeSwitcher(
        "v3_hybrid",
        risk_pct=0.8,
        tightness_percentile=20, # Initial default
        max_inventory=100,
        margin_cents=4.0,        # Initial default
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )
    return strategy


class SmoothRegimeSwitcher(RegimeSwitcher):
    """
    Scales margin linearly with spread to avoid binary "traps".
    margin = base_margin + (spread * spread_factor)
    """
    def __init__(self, name, base_margin=4.0, spread_factor=0.5, **kwargs):
        super().__init__(name, **kwargs)
        self.base_margin = base_margin
        self.spread_factor = spread_factor
        
    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        yes_ask = market_state.get('yes_ask')
        yes_bid = market_state.get('yes_bid')
        if yes_ask is not None and yes_bid is not None:
            spread = yes_ask - yes_bid
            # Linear scaling: e.g. Base 2c + (0.5 * Spread)
            # Spread 4c -> Margin 4c
            # Spread 10c -> Margin 7c (easier to exit than 10c)
            self.mm.margin_cents = self.base_margin + (spread * self.spread_factor)
            
        return super().on_market_update(ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx)


def smooth_v3(base_margin=2.0, spread_factor=0.5) -> RegimeSwitcher:
    # "The Smooth Operator": Scales difficulty with market conditions.
    return SmoothRegimeSwitcher(
        f"v3_smooth_b{base_margin}_f{spread_factor}",
        base_margin=base_margin,
        spread_factor=spread_factor,
        risk_pct=0.8,
        tightness_percentile=50, # Loose gate, rely on dynamic margin
        max_inventory=100,
        scaling_factor=4.0,
        max_notional_pct=0.10,
        max_loss_pct=0.03,
    )
