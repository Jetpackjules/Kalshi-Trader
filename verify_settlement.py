
import datetime
from unified_engine.engine import UnifiedEngine
from unified_engine.adapters import SimAdapter
import inspect

class MockStrategy:
    def __init__(self):
        self.name = "MockStrategy"
    
    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        # Buy YES on KXHIGHNY-26JAN08 if not already bought
        if ticker == "KXHIGHNY-26JAN08" and inventories.get("MM", {}).get("YES", 0) == 0:
            return [{"action": "BUY_YES", "ticker": ticker, "qty": 10, "price": 50, "expiry": current_time + datetime.timedelta(minutes=1), "source": "MM", "time": current_time}]
        return []

def test_settlement():
    adapter = SimAdapter(initial_cash=10000.0)
    engine = UnifiedEngine(adapter=adapter, strategy=MockStrategy(), decision_log=None)
    
    # 1. Feed a tick to trigger a buy
    tick_time = datetime.datetime(2026, 1, 8, 20, 0, 0)
    ticker = "KXHIGHNY-26JAN08"
    market_state = {"yes_ask": 50, "yes_bid": 48, "no_ask": 52, "no_bid": 50}
    
    print(f"Initial Cash: {adapter.cash}")
    print(f"Signature: {inspect.signature(engine.on_tick)}")
    
    engine.on_tick(ticker=ticker, market_state=market_state, current_time=tick_time)
    
    # Verify trade happened
    pos = adapter.get_positions().get(ticker)
    print(f"Position after trade: {pos}")
    if not pos or pos['yes'] != 10:
        print("FAILED: Trade did not execute")
        return

    print(f"Cash after trade: {adapter.cash}") # Should be 10000 - 500 = 9500 (approx)
    
    # 2. Advance time to Settlement (Jan 9 5 AM)
    # We need to feed a tick with time > settlement time
    settle_time = datetime.datetime(2026, 1, 9, 5, 1, 0)
    
    # We need to ensure 'last_prices' has a price for settlement.
    # The engine updates last_prices on every tick.
    # Let's say the market closes at 100 (YES outcome).
    final_market_state = {"yes_ask": 99, "yes_bid": 99, "no_ask": 1, "no_bid": 1}
    
    print("Triggering settlement...")
    engine.on_tick(ticker=ticker, market_state=final_market_state, current_time=settle_time)
    
    # 3. Verify Settlement
    pos_after = adapter.get_positions().get(ticker)
    print(f"Position after settlement: {pos_after}")
    print(f"Cash after settlement: {adapter.cash}")
    
    if pos_after is None and adapter.cash >= 10000.0: # Should be 9500 + 1000 = 10500
        print("SUCCESS: Settlement verified!")
    else:
        print("FAILED: Settlement did not occur correctly")

if __name__ == "__main__":
    test_settlement()
