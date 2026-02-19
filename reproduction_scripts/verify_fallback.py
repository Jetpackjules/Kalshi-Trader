
import sys
import os
from datetime import datetime, date
from zoneinfo import ZoneInfo

# Add server_mirror to path
sys.path.append(os.path.abspath("server_mirror"))

from backtesting.strategies.nws_regime_split_f6_0322 import NWSRegimeSplitF60322Trader

def verify_fallback():
    # Setup parameters matching "champion_live_current"
    # decision_anchor_mode="rolling_latest" isn't relevant to _resolve_forecast_for_target internal logic
    # but forecast_delay_minutes=0 IS relevant.
    print("--- Initializing Strategy with forecast_delay_minutes=0 ---")
    strategy = NWSRegimeSplitF60322Trader(
        forecast_delay_minutes=0,
        mos_station="KNYC", # Default
        model="NAM" # Default
    )

    # Target Date: Feb 16, 2026
    # Decision Anchor: Feb 15, 2026 17:00 EST (The critical decision time)
    tz = ZoneInfo("America/New_York")
    target_day = date(2026, 2, 16)
    decision_anchor = datetime(2026, 2, 15, 17, 0, 0, tzinfo=tz)

    print(f"Target Day: {target_day}")
    print(f"Decision Anchor: {decision_anchor} (Local)")
    # Removed problematic UTC print to avoid Windows OSError

    print("\n--- executing _resolve_forecast_for_target ---")
    forecast, runtime = strategy._resolve_forecast_for_target(
        target_day=target_day,
        decision_anchor_local=decision_anchor
    )

    print("\n--- RESULTS ---")
    if forecast is not None:
        print(f"Forecast Found: {forecast:.2f} F")
        print(f"Runtime Used: {runtime}")
        
        # Verify if it used the fallback
        # 17:00 EST = 22:00 UTC. Floored 6h = 18:00 UTC.
        # If 18z is missing, it should have used 12z.
        expected_primary = datetime(2026, 2, 15, 18, 0, 0, tzinfo=datetime.now().astimezone().tzinfo).replace(tzinfo=None) # naive check
        # Actually runtime comes back as naive UTC-like from the strategy usually or timezone aware? 
        # strategy._parse_utc_timestamp returns UTC aware.
        
        runtime_str = runtime.strftime("%Y-%m-%d %H:%M UTC")
        if "12:00" in runtime_str:
            print("SUCCESS: Fallback to 12z confirmed!")
        elif "18:00" in runtime_str:
            print("WARNING: It used 18z. Did 18z become available?")
        else:
            print(f"Used unexpected runtime: {runtime_str}")

    else:
        print("FAILURE: No forecast found.")

if __name__ == "__main__":
    verify_fallback()
