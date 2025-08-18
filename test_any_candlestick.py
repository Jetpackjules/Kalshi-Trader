#!/usr/bin/env python3
"""
Test candlestick data with any available market
"""

import requests
import time
import base64
import json
from datetime import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def test_any_candlestick():
    api_key = "8adbb05c-01ca-42cf-af00-f05e551f0c25"
    
    # Load from file instead
    with open('/home/jetpackjules/kalshi-wsl/kalshi_private_key.pem', 'r') as f:
        private_key_pem = f.read()
    
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    
    # Get events and find an active market
    path = "/events"
    timestamp = str(int(time.time() * 1000))
    message = timestamp + "GET" + path
    
    signature = private_key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.b64encode(signature).decode()
    
    headers = {
        'KALSHI-ACCESS-KEY': api_key,
        'KALSHI-ACCESS-TIMESTAMP': timestamp,
        'KALSHI-ACCESS-SIGNATURE': signature_b64,
        'User-Agent': 'candlestick-test/1.0',
        'Accept': 'application/json'
    }
    
    url = f"https://api.elections.kalshi.com/trade-api/v2{path}"
    response = requests.get(url, headers=headers, params={'limit': 10})
    
    if response.status_code != 200:
        print(f"Error getting events: {response.status_code}")
        return
    
    data = response.json()
    events = data.get('events', [])
    
    # Find first active market
    test_market = None
    series_ticker = None
    
    for event in events:
        markets = event.get('markets', [])
        for market in markets:
            if market.get('status') == 'open' and market.get('last_price') is not None:
                test_market = market
                series_ticker = event.get('event_ticker')
                break
        if test_market:
            break
    
    if not test_market:
        print("❌ No active markets with prices found")
        return
    
    ticker = test_market.get('ticker', '')
    print(f"🎯 Testing with active market: {ticker}")
    print(f"   Last price: ${test_market.get('last_price', 'N/A')}")
    
    # Test candlesticks
    now = int(time.time())
    start_ts = now - (7 * 24 * 3600)  # 7 days ago
    end_ts = now
    
    path = f"/series/{series_ticker}/markets/{ticker}/candlesticks"
    timestamp = str(int(time.time() * 1000))
    message = timestamp + "GET" + path
    
    signature = private_key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.b64encode(signature).decode()
    
    headers = {
        'KALSHI-ACCESS-KEY': api_key,
        'KALSHI-ACCESS-TIMESTAMP': timestamp,
        'KALSHI-ACCESS-SIGNATURE': signature_b64,
        'User-Agent': 'candlestick-test/1.0',
        'Accept': 'application/json'
    }
    
    candlestick_url = f"https://api.elections.kalshi.com/trade-api/v2{path}"
    params = {
        'start_ts': start_ts,
        'end_ts': end_ts,
        'period_interval': 1440  # Daily
    }
    
    print(f"📊 Getting candlesticks for {ticker} (last 7 days)")
    response = requests.get(candlestick_url, headers=headers, params=params)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        candlestick_data = response.json()
        candlesticks = candlestick_data.get('candlesticks', [])
        print(f"Found {len(candlesticks)} candlesticks")
        
        if candlesticks:
            print("\nFirst candlestick:")
            print(json.dumps(candlesticks[0], indent=2))
        else:
            print("No candlestick data available")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    test_any_candlestick()