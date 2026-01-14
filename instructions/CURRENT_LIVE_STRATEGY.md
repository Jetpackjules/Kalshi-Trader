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

## Plain English Explanation (ELI5)
**"The Picky Bargain Hunter"**

1.  **The Gatekeeper (Tightness):** It watches the market like a hawk. It only wakes up when the "Yes" and "No" prices are very close together (the tightest 10% of the time). This ensures it only trades when the market is liquid and "fair".
2.  **The Discount (Margin):** It calculates the "fair price" based on recent history. It **refuses to buy** unless it gets a discount of at least **8 cents** cheaper than that fair price. It's like refusing to buy a $1 candy bar unless it's on sale for 92 cents.
3.  **The Schedule (Hours):** It only works during specific "business hours" (Morning, Afternoon, Night) when other traders are active. It sleeps during lunch and overnight to avoid weird price spikes.
4.  **The Bet (Sizing):** If it finds a small discount, it buys a little. If it finds a HUGE discount, it buys A LOT (up to 10% of your cash at once).
