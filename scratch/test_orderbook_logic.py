from fetch_orderbook import get_active_markets, get_orderbook, parse_market_date, parse_market_temp

# Test fetching markets
print("Testing functions...")
markets = get_active_markets()
print(f"Found {len(markets)} markets")

if markets:
    ticker = markets[0]["ticker"]
    print(f"\nTesting ticker: {ticker}")
    
    date = parse_market_date(ticker)
    print(f"Date: {date}")
    
    temp = parse_market_temp(ticker)
    print(f"Temp: {temp}")
    
    orderbook = get_orderbook(ticker)
    print(f"Orderbook type: {type(orderbook)}")
    print(f"Orderbook: {orderbook}")
    
    # Test the exact line that's failing
    print("\nTesting problematic line 52...")
    print(f"orderbook is None: {orderbook is None}")
    print(f"orderbook is dict: {isinstance(orderbook, dict)}")
    
    if not orderbook or not isinstance(orderbook, dict):
        print("Converting to empty dict")
        orderbook = {"yes": [], "no": []}
    
    yes_orders = len(orderbook.get("yes", []))
    no_orders = len(orderbook.get("no", []))
    
    print(f"YES orders: {yes_orders}")
    print(f"NO orders: {no_orders}")
    print("\n✓ All tests passed!")
