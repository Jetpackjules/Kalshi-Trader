from __future__ import annotations

from backtesting.strategies.champion_f6_0322_equity_target import NWSRegimeSplitF60322EquityTargetTrader

class NWSRegimeSplitF60322ColdOnlyTrader(NWSRegimeSplitF60322EquityTargetTrader):
    """
    Variant of the Champion Equity Target strategy that forces "Cold Regime" logic
    (Step = -2) for ALL temperatures.
    """
    def __init__(self, **kwargs):
        # Force the thresholds to extreme values so EVERYTHING falls into the "Cold" bucket (< t1).
        # t1 is normally ~36.9F. We set it to 200F so all valid forecasts are < t1.
        kwargs["t1"] = 200.0
        kwargs["t2"] = 300.0 # Just to maintain t2 > t1 invariant
        
        # Ensure step_cold is -2 (default, but explicit for safety)
        kwargs["step_cold"] = -2
        
        super().__init__(**kwargs)

def champion_cold_only(**kwargs):
    cfg = dict(kwargs)
    cfg.setdefault("name", "champion_cold_only")
    cfg.setdefault("decision_anchor_mode", "rolling_latest")
    cfg.setdefault("forecast_delay_minutes", 0)
    cfg.setdefault("cash_fraction", 0.5)
    return NWSRegimeSplitF60322ColdOnlyTrader(**cfg)
