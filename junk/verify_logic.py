import pandas as pd
from datetime import datetime
from multi_strategy_backtest import InventoryAwareMarketMaker, HumanReadableBacktester

# Mock Classes
class MockWallet:
    def __init__(self):
        self.available_cash = 100000
    def spend(self, amt):
        self.available_cash -= amt
        return True
    def add_cash(self, amt):
        self.available_cash += amt
    def get_total_equity(self):
        return self.available_cash

def test_strategy_logic():
    print("=== Testing Strategy 2.5 Logic ===")
    
    # 1. Setup Strategy
    strat = InventoryAwareMarketMaker("TestMM", risk_pct=0.5, max_offset=2)
    strat.fair_price = 50.0 # Force fair price
    
    # 2. Setup Market Snapshot
    # Spread: 48-52 (Mid 50)
    # MM should quote inside: Buy 49, Sell 51 (Buy No 49)
    current_time = datetime(2025, 1, 1, 12, 0, 0)
    
    snapshot = {
        'TICKER': {
            'yes_ask': 52.0,
            'no_ask': 52.0, # Bid 48
            'implied_yes_ask': 52.0, # Legacy key just in case
            'implied_no_ask': 52.0
        }
    }
    
    holdings = []
    
    # 3. Run on_snapshot (Generate Orders)
    orders = strat.on_snapshot(snapshot, current_time, holdings)
    print(f"Generated {len(orders)} orders:")
    for o in orders:
        print(f" - {o['action']} @ {o['price']}")
        
    if not orders:
        print("FAIL: No orders generated")
        return

    # 4. Setup Backtester for Fills
    bt = HumanReadableBacktester()
    portfolio = {
        'active_limit_orders': orders,
        'wallet': MockWallet(),
        'cash': 100000,
        'holdings': [],
        'trades': [],
        'spent_today': 0
    }
    
    # 5. Simulate Market Move to FILL the buy order
    # Move market down: Ask becomes 48.
    # My Bid is 49. Ask 48 <= Bid 49. FILL!
    snapshot_fill = {
        'TICKER': {
            'yes_ask': 48.0, # Crashed
            'no_ask': 60.0,
            'yes_bid': 40.0,
            'no_bid': 52.0
        }
    }
    
    daily_trades_viz = []
    
    print("\nChecking Fills...")
    bt.check_limit_fills(portfolio, snapshot_fill, current_time, daily_trades_viz, "TestMM")
    
    # 6. Verify Trade
    print(f"Trades Generated: {len(portfolio['trades'])}")
    if len(portfolio['trades']) > 0:
        print("SUCCESS: Trade Executed!")
        print(portfolio['trades'][0])
    else:
        print("FAIL: No trade executed")

if __name__ == "__main__":
    test_strategy_logic()
