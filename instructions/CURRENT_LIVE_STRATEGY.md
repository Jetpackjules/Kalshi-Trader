# Current Live Strategy

**Status:** ACTIVE
**Deployed:** 2026-01-11
**Strategy Name (Code):** `recommended_live_strategy`
**Internal Variant:** `grid_r80_n10_m8_t10_s2`

## Parameters
*   **Risk %:** 0.8 (80% of daily budget)
*   **Max Notional %:** 0.10 (10% of cash per trade)
*   **Margin Cents:** 8.0 (Requires 8c edge above fees)
*   **Tightness Percentile:** 10 (Only trades tightest 10% of spreads)
*   **Scaling Factor:** 2.0 (Aggressive sizing ramp)
*   **Max Inventory:** 150 contracts

## Deployment Info
*   **Entry Point:** `unified_engine.runner` (default arg)
*   **Definition:** `server_mirror/backtesting/strategies/v3_variants.py`
*   **Logs:** `~/output.log` on VM
