import json
import os
import sys
from live_trader_v4 import LiveTraderV4

def export_state():
    print("Initializing LiveTraderV4 to fetch state...")
    try:
        trader = LiveTraderV4()
        # Force sync to get latest from API
        trader.sync_api_state(force_reset_daily=False)
        
        state = {
            "balance": trader.balance,
            "portfolio_value": trader.portfolio_value,
            "positions": trader.positions,
            "daily_start_equity": trader.daily_start_equity,
            "timestamp": trader.last_status_time.isoformat() if trader.last_status_time else None
        }
        
        with open("live_state.json", "w") as f:
            json.dump(state, f, indent=2)
            
        print("Successfully exported state to live_state.json")
        print(json.dumps(state, indent=2))
        
    except Exception as e:
        print(f"Error exporting state: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    export_state()
