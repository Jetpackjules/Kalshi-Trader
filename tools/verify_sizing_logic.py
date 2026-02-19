
import sys
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

# Add root and server_mirror to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "server_mirror"))

try:
    from server_mirror.unified_engine.adapters import LiveAdapter
    from server_mirror.backtesting.strategies.champion_f6_0322_equity_target import NWSRegimeSplitF60322EquityTargetTrader
    from server_mirror.unified_engine.engine import UnifiedEngine
except ImportError:
    # Try alternate path structure if running from tools/
    sys.path.append(os.path.join(os.getcwd(), ".."))
    sys.path.append(os.path.join(os.getcwd(), "..", "server_mirror"))
    from server_mirror.unified_engine.adapters import LiveAdapter
    from server_mirror.backtesting.strategies.champion_f6_0322_equity_target import NWSRegimeSplitF60322EquityTargetTrader
    from server_mirror.unified_engine.engine import UnifiedEngine

def verify_fix():
    print("--- Verifying Position Sizing Logic Fix ---")
    
    # 1. Initialize Adapter & Strategy
    key_path = "kalshi_prod_private_key.pem"
    if not os.path.exists(key_path):
        key_path = os.path.expanduser("~/kalshi_prod_private_key.pem")
    
    print(f"Using Key: {key_path}")
    adapter = LiveAdapter(key_path=key_path)
    
    strategy = NWSRegimeSplitF60322EquityTargetTrader(
        cash_fraction=0.5,
        decision_anchor_mode="rolling_latest"
    )
    
    # 2. Fetch Live State
    print("Fetching Live State...")
    cash = float(adapter.get_cash())
    positions = adapter.get_positions()
    
    ticker = "KXHIGHNY-26FEB19-T40" # The one we traded
    
    print(f"\nLive Data:")
    print(f"  Cash: ${cash:.2f}")
    print(f"  Positions Raw: {json.dumps(positions.get(ticker, {}))}")
    
    # 3. Simulate Engine Logic (Global State Passing)
    # Replicating the PATCHED logic from engine.py
    portfolios_inventories = {}
    for tkr, pos in positions.items():
        portfolios_inventories[tkr] = {
            "yes": int(pos.get("yes") or 0),
            "no": int(pos.get("no") or 0),
        }
    
    # In engine.py, we overlay pending. Here assuming 0 pending for test.
    
    print(f"\nConstructed Inventory (passed to strategy):")
    print(f"  {json.dumps(portfolios_inventories.get(ticker, {}))}")
    
    # 4. Simulate Strategy Decision
    print("\n--- Running Strategy Logic ---")
    
    # Mock Market State (we need a price to value the position)
    # Using 81c as a dummy ask/bid to simulate valuation
    market_state = {
        "yes_ask": 99,
        "yes_bid": 20,
        "no_ask": 81, # Asking 81c
        "no_bid": 75
    }
    
    # Force strategy to look at THIS ticker
    # We need to inject the market date for the strategy to recognize it
    target_date = datetime(2026, 2, 19).date()
    # Mocking ALL tickers for the rollout to pass the "waiting_full_snapshot" check
    tickers = [
        "KXHIGHNY-26FEB19-T39",
        "KXHIGHNY-26FEB19-T40",
        "KXHIGHNY-26FEB19-T41",
        "KXHIGHNY-26FEB19-T42",
        "KXHIGHNY-26FEB19-T43",
        "KXHIGHNY-26FEB19-T44",
    ]
    for t in tickers:
        strategy._ticker_market_date[t] = target_date
        strategy._latest_yes_ask[t] = 99
        strategy._latest_no_ask[t] = 81
    
    # Mock the specific one we hold position in
    strategy._latest_no_ask[ticker] = 81 

    # Mock Current Time (2:00 PM PT = 5:00 PM ET)
    # Strategy expects LA time
    now = datetime(2026, 2, 18, 14, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

    # Monkey-patch internal methods to bypass data fetching and force execution path
    # We want to test logic: "Target T40 -> See Position -> budget <= 0"
    
    # 1. Bypass Contract Parsing
    strategy._build_contract_defs = lambda tickers: [1, 2, 3, 4, 5, 6] # Just needs length >= 6
    
    # 2. Bypass Forecast Fetching
    # Return (Forecast, Runtime)
    strategy._resolve_forecast_for_target = lambda target_day, decision_anchor_local: (40.0, datetime.utcnow())
    
    # 3. Bypass Regime/Step Logic
    # Force it to pick NO on T40
    # The strategies logic for Step -2 (Cold) on T40 (Strike 40) is complex.
    # Simpler to just force _regime_params and _step_ticker.
    
    # Force "NO" side
    strategy._regime_params = lambda forecast: ("NO", -2) 
    
    # Force it to pick our ticker
    strategy._step_ticker = lambda forecast, defs, step: ticker

    # Run
    orders = strategy.on_market_update(
        ticker,
        market_state,
        now,
        portfolios_inventories,
        [], # No active orders
        cash
    )
    
    # 5. Report Results
    print("\n--- Result ---")
    print(f"Last Gate Reason: {strategy.last_gate_reason}")
    print(f"Last Gate Detail: {strategy.last_gate_detail}")
    
    # Calculate expected values manually to verify
    # Value of 18 NO contracts @ 81c = $14.58
    # Total Equity = Cash ($0.30) + $14.58 = $14.88
    # Target (50%) = $7.44
    # Current Exposure = $14.58
    # Budget = $7.44 - $14.58 = -$7.14
    
    print(f"\nInterpretation:")
    if strategy.last_gate_reason == "max_exposure_reached":
        print("✅ SUCCESS: Strategy correctly identified max exposure was reached.")
    elif strategy.last_gate_reason == "no_cash_budget":
        # This might happen if 'budget' calculation goes negative and is clamped?
        # In the patch: budget = min(cash, target - current)
        # If target < current, target - current is negative.
        # So budget is negative. 
        # The check `if budget <= 0` catches it.
        # But wait, did I change the gate reason in the patch?
        # Yes: self.last_gate_reason = "max_exposure_reached"
        pass
    else:
        print(f"❌ FAILURE: Unexpected reason: {strategy.last_gate_reason}")

if __name__ == "__main__":
    verify_fix()
