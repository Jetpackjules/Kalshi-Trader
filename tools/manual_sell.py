import sys
import os
import time
from datetime import datetime

# Add root to path
sys.path.append(os.getcwd())

try:
    from server_mirror.unified_engine.adapters import LiveAdapter, OrderResult
    from server_mirror.backtesting.strategies.simple_market_maker import Order
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), ".."))
    from server_mirror.unified_engine.adapters import LiveAdapter, OrderResult
    from server_mirror.backtesting.strategies.simple_market_maker import Order

def manual_sell():
    print("--- Manual Sell Test ---")
    key_path = "keys/kalshi_prod_private_key.pem"
    
    try:
        adapter = LiveAdapter(key_path=key_path)
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # Target: Sell 50 YES of KXHIGHNY-26JAN24-B22.5
    # To Sell YES, we Buy NO.
    # User wants to limit sell at 5c (YES price).
    # So we limit buy NO at 95c.
    
    ticker = "KXHIGHNY-26JAN24-B22.5"
    qty = 50
    yes_price = 5
    no_price = 100 - yes_price # 95
    
    print(f"Target: {ticker}")
    print(f"Action: SELL YES (by Buying NO)")
    print(f"Qty: {qty}")
    print(f"Limit Price (YES): {yes_price}c")
    print(f"Limit Price (NO):  {no_price}c")
    
    # Construct Order Object (Mock)
    class MockOrder:
        def __init__(self, action, ticker, qty, price):
            self.action = action
            self.ticker = ticker
            self.qty = qty
            self.price = price
            self.source = "MANUAL"

    # Action is BUY_NO
    order = MockOrder("BUY_NO", ticker, qty, no_price)
    
    print("\nPlacing Order...")
    result = adapter.place_order(order, {}, datetime.now())
    
    print(f"Result: {result}")
    
    if result.ok:
        print("Order placed successfully.")
    else:
        print("Order failed.")

if __name__ == "__main__":
    manual_sell()
