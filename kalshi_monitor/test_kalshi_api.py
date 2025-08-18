#!/usr/bin/env python3
"""
Test script to check Kalshi API access
"""

import requests
import json

def test_kalshi_endpoints():
    """Test different Kalshi API endpoints"""
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'kalshi-test/1.0 (test@example.com)',
        'Accept': 'application/json'
    })
    
    endpoints_to_test = [
        "https://trading-api.kalshi.com/trade-api/v2/events",
        "https://trading-api.kalshi.com/trade-api/v2/markets", 
        "https://api.kalshi.com/v1/events",
        "https://api.kalshi.com/v1/markets"
    ]
    
    for endpoint in endpoints_to_test:
        print(f"\n🔍 Testing: {endpoint}")
        
        try:
            response = session.get(endpoint, params={'limit': 1})
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Success! Keys: {list(data.keys())}")
                
                # Look for temperature markets
                if 'events' in data:
                    events = data['events'][:3]  # First 3 events
                    for event in events:
                        title = event.get('title', 'N/A')
                        ticker = event.get('event_ticker', 'N/A')
                        print(f"  Event: {ticker} - {title}")
                        
                elif 'markets' in data:
                    markets = data['markets'][:3]  # First 3 markets
                    for market in markets:
                        title = market.get('title', 'N/A')
                        ticker = market.get('ticker', 'N/A')
                        print(f"  Market: {ticker} - {title}")
                        
            elif response.status_code == 401:
                print("❌ 401 Unauthorized - API requires authentication")
            else:
                print(f"❌ Error {response.status_code}: {response.text[:200]}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")

if __name__ == "__main__":
    print("🌡️ Testing Kalshi API Access")
    print("=" * 50)
    test_kalshi_endpoints()