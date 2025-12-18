import datetime
from fetch_weather_markets import fetch_market_history

def test_history():
    # Use a market and date from the user's screenshot
    ticker = "KXHIGHNY-25NOV19-T52"
    date_obj = datetime.date(2025, 11, 19)
    
    print(f"Testing history fetch for {ticker} on {date_obj}")
    
    history = fetch_market_history(ticker, date_obj)
    
    print(f"Result: {len(history)} data points found.")
    if history:
        print("First point:", history[0])
        print("Last point:", history[-1])

if __name__ == "__main__":
    test_history()
