from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from server_mirror.backtesting.strategies.champion_f6_0322_equity_target import champion_live_current

t = champion_live_current()
now = datetime.now()
# Force 17:01 EST to pass the clock guard
now_local = now.replace(hour=17, minute=1, second=0).astimezone(ZoneInfo("America/New_York"))

print("Running test...")
t.on_market_update(
    "KXHIGHNY-26FEB22-T39",
    {"yes_ask": 50, "no_ask": 50}, # market_state
    now_local, # current_time
    {}, # portfolios_inventories
    [], # active_orders
    10.0 # cash
)
print("Last Gate Reason:", getattr(t, "last_gate_reason", None))
print("Done!")
