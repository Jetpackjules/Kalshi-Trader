import datetime
import kalshi_python

def test_sdk():
    key_id = "7a266d00-7db2-4c35-90e0-477b739fac06"
    with open("kalshi_private_key.pem", "r") as f:
        private_key = f.read()
        
    print("Creating configuration...")
    config = kalshi_python.Configuration()
    config.api_key_id = key_id
    config.private_key = private_key
    
    print("Initializing Kalshi Client...")
    client = kalshi_python.KalshiClient(configuration=config)
    print("Client initialized success fully!")
    
    # Create MarketsApi instance
    print("\nCreating MarketsApi...")
    markets_api = kalshi_python.MarketsApi(client)
    
    # Test fetching market candles
    ticker = "KXHIGHNY-25NOV19-T52"
    print(f"\nFetching candles for {ticker}...")
    
    try:
        start_dt = datetime.datetime(2025, 11, 19, tzinfo=datetime.timezone.utc)
        end_dt = start_dt + datetime.timedelta(days=1)
        
        response = markets_api.get_market_candlesticks(
            ticker=ticker
        )
        
        print(f"Success! Response type: {type(response)}")
        if hasattr(response, 'candlesticks'):
            print(f"Got {len(response.candlesticks)} candles")
            if response.candlesticks:
                candle = response.candlesticks[0]
                print(f"First candle: close={candle.close}, volume={candle.volume}, end_period={candle.end_period}")
        else:
            print(f"Response: {response}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_sdk()
