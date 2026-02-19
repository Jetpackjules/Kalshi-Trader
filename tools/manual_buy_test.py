import sys
import os
from datetime import datetime

# Add root to path
sys.path.append(os.getcwd())

try:
    from server_mirror.unified_engine.adapters import LiveAdapter, OrderResult
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), ".."))
    from server_mirror.unified_engine.adapters import LiveAdapter, OrderResult

class Order:
    def __init__(self, action, ticker, qty, price):
        self.action = action
        self.ticker = ticker
        self.qty = qty
        self.price = price
        self.source = "MANUAL_TEST"

def manual_buy_test():
    print("--- Manual Buy Test (1 Share) ---")
    
    # Check for key file compatibility
    # User's key is at ~/kalshi_prod_private_key.pem usually, but script might run locally on Windows
    # The run_bot.sh uses ~/kalshi_prod_private_key.pem
    # Provide an option or default to a local path if it exists
    if os.path.exists("kalshi_prod_private_key.pem"):
        key_path = "kalshi_prod_private_key.pem"
    else:
        # Fallback to User Profile if on Windows
        key_path = os.path.expanduser("~/kalshi_prod_private_key.pem")
    
    print(f"Using Key Path: {key_path}")

    try:
        adapter = LiveAdapter(key_path=key_path)
        print("Adapter Initialized.")
    except Exception as e:
        print(f"Error initializing adapter: {e}")
        return

    # Target: KXHIGHNY-26FEB19-T40
    # Action: BUY NO
    # Price: Previous logs showed Ask around 81c. 
    # To be safe and likely get a fill or at least a valid resting order, 
    # we can use a limit price. 
    # The bot tried 81c. Let's try 80c or 81c. 
    # Or asking user preference? "run the same trade command... for only 1 share"
    # The bot's command was: BUY_NO 8x KXHIGHNY-26FEB19-T40 @ 99 (It used market_order_price=99 for high confidence)
    
    ticker = "KXHIGHNY-26FEB19-T40"
    qty = 1
    price = 99 # Replicate the bot's "Market" style limit price
    action = "BUY_NO"

    print(f"Target: {ticker}")
    print(f"Action: {action}")
    print(f"Qty: {qty}")
    print(f"Price: {price}")
    
    order = Order(action, ticker, qty, price)
    
    print("\nPlacing Order...")
    # market_state is optional for LiveAdapter but good practice to pass empty dict if unknown
    market_state = {} 
    
    result = adapter.place_order(order, market_state, datetime.now())
    
    print(f"Result: {result}")
    
    if result.ok:
        print("Order placed successfully.")
    else:
        print(f"Order failed: {result.status}")

if __name__ == "__main__":
    manual_buy_test()
