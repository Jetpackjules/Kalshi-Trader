#!/usr/bin/env python3
"""
NYC Temperature Betting History using Official Kalshi Python SDK
Uses the kalshi-python package from PyPI: https://pypi.org/project/kalshi-python/
"""

import kalshi_python
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json


def search_temperature_markets(market_api) -> Dict:
    """Search for temperature and weather related markets using the official SDK"""
    
    print("🔍 Searching for temperature/weather markets using official SDK...")
    
    # Get all events first
    try:
        events_response = market_api.get_events()
        # The SDK returns an object, so we need to get the data
        events = events_response.events if hasattr(events_response, 'events') else []
    except Exception as e:
        print(f"Error getting events: {e}")
        return {"events": [], "markets": []}
    
    print(f"📋 Found {len(events)} total events on Kalshi")
    
    # Filter for weather/temperature/NYC related events
    weather_keywords = [
        'temperature', 'weather', 'climate', 'hot', 'cold', 'heat',
        'high', 'low', 'degrees', 'celsius', 'fahrenheit',
        'nyc', 'new york', 'york'
    ]
    
    relevant_events = []
    
    for event in events:
        title = event.get('title', '').lower()
        ticker = event.get('event_ticker', '').lower()
        category = event.get('category', '').lower()
        
        event_text = f"{title} {ticker} {category}"
        
        if any(keyword in event_text for keyword in weather_keywords):
            relevant_events.append(event)
            print(f"  ✓ Found: {event.get('event_ticker')} - {event.get('title')}")
    
    print(f"🌡️ Found {len(relevant_events)} weather/temperature related events")
    
    # Get markets for relevant events
    all_markets = []
    
    for event in relevant_events[:10]:  # Limit to avoid rate limits
        event_ticker = event.get('event_ticker') if hasattr(event, 'get') else event.event_ticker
        try:
            markets_response = market_api.get_markets(event_ticker=event_ticker)
            markets = markets_response.markets if hasattr(markets_response, 'markets') else []
            
            for market in markets:
                # Convert to dict for easier handling
                market_dict = market.to_dict() if hasattr(market, 'to_dict') else market
                market_dict['parent_event'] = event.to_dict() if hasattr(event, 'to_dict') else event
                all_markets.append(market_dict)
                
        except Exception as e:
            print(f"Error getting markets for {event_ticker}: {e}")
    
    print(f"📊 Found {len(all_markets)} total markets")
    
    return {
        "events": relevant_events,
        "markets": all_markets
    }


def search_for_nhigh_specifically(market_api) -> Dict:
    """Specifically search for NHIGH (NYC High temperature) markets"""
    
    print("🎯 Specifically searching for NHIGH (NYC High) markets...")
    
    # Try to get events for NHIGH series
    try:
        events_response = market_api.get_events(series_ticker="NHIGH")
        events = events_response.events if hasattr(events_response, 'events') else []
        
        if events:
            print(f"✓ Found {len(events)} NHIGH events!")
            
            all_markets = []
            for event in events:
                try:
                    event_ticker = event.get('event_ticker') if hasattr(event, 'get') else event.event_ticker
                    markets_response = market_api.get_markets(event_ticker=event_ticker)
                    markets = markets_response.markets if hasattr(markets_response, 'markets') else []
                    for market in markets:
                        market_dict = market.to_dict() if hasattr(market, 'to_dict') else market
                        all_markets.append(market_dict)
                except Exception as e:
                    event_ticker = event.get('event_ticker') if hasattr(event, 'get') else getattr(event, 'event_ticker', 'unknown')
                    print(f"Error getting markets for {event_ticker}: {e}")
            
            return {"events": events, "markets": all_markets}
        else:
            print("❌ No NHIGH events found")
            return {"events": [], "markets": []}
            
    except Exception as e:
        print(f"Error searching for NHIGH: {e}")
        return {"events": [], "markets": []}


def analyze_historical_data(markets: List[Dict]) -> pd.DataFrame:
    """Analyze historical market data"""
    
    if not markets:
        return pd.DataFrame()
    
    print(f"📈 Analyzing {len(markets)} markets for historical data...")
    
    results = []
    
    for market in markets:
        result_data = {
            'market_ticker': market.get('ticker', ''),
            'subtitle': market.get('subtitle', ''),
            'status': market.get('status', ''),
            'result': market.get('result', ''),
            'last_price': market.get('last_price'),
            'volume': market.get('volume', 0),
            'close_time': market.get('close_time', ''),
            'event_ticker': market.get('parent_event', {}).get('event_ticker', ''),
            'event_title': market.get('parent_event', {}).get('title', ''),
            'category': market.get('parent_event', {}).get('category', '')
        }
        results.append(result_data)
    
    df = pd.DataFrame(results)
    
    # Filter for settled/closed markets with results
    if not df.empty:
        settled_df = df[df['status'].isin(['settled', 'closed', 'finalized'])]
        if not settled_df.empty:
            print(f"✓ Found {len(settled_df)} settled markets with historical data")
            return settled_df
        else:
            print("❌ No settled markets found (no historical betting results)")
    
    return df


def main():
    # Your API credentials
    API_KEY_ID = "db5ced1d-0df9-4398-ac0c-83d281e1c6b2"
    PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA5cCcLE45c2d/OzgE6V82DmK1XPFk9TFTSMlJDYLJIrpr5jGT
Oa5aMqxztG2EspAhyxEkh9WswO/SZY9Zr5mw4eeofROhzUSeFEPhR2Wfoc6AamOp
wU6au5MJObUZfrjgGUsX3ZTqxUtLqQ476bxw7I8/yn39YiWCAna0yJ1Y/uCSJO4D
pfwfFHbhunpTj1aiONXixm0SUPHwaBJVZt2pciYMMlKTozL5lElTDwmFaGFjr31F
DVRRGY23b/I5DjNQ0sBVXk8Hz3GE13Usb3CP0FhToR83HBmjQMRWBxpIXOikD1i3
FSsWGUsGyU0jAkRdwXVZ/CGyF1xndn2bt5zTMQIDAQABAoIBAQDRjlzkDHVaTYw+
91mDgtRLSr0hiQwMmHDecrmvGRtcEa1YyN8APYcHsUPXzgy60bwA/CHVw49Oa2/8
MkQbZpNveVy0uLNcBroowcE43fg8HZ4Da+Pp7Ug0zmgbupMGgpnkeBnMgYehbIwW
JmV/S+Gz4vTMPR5f5tYuaRd75AjIb1Jib2doLKCvoAKZL84IF7i6fx9xyGcvdPT3
hx0b6SGgX06pGsf4y+F6fZcZhCFdtIOo/nfmdnB17o0awqXYU0K+3l5VnZHOnXr0
NY3eHqaEk8MJmfBUi9nqqbnvnP687RKG3jmKobhY/sL1G2pUEwoPuWaJn5PfkGDt
srRBuGgBAoGBAO5NFBRzs1vd6ydC5EQ0fdj+BFLPTgWHuT8tZpSZdToek4bsvQP2
yWATrAm3Sry2uZsXGsd6QsQ4S8BG3KBeLQhU92mQyuD0FY50VVZbh/loAnWeQkRm
TQ3ZNY9XUvdJINeXS1i/SjNuSxq14tgf+IdU1sPh7+PFr02ZiVjADVglAoGBAPbQ
/cxJONPPwlTPFD9a9Y/d7+AQcOVaGDGWO9YICVYRyWlHU0udhtCRM2mWHwLuIrUC
LKDGH/qZll9GWDKcUdDpFhbi6auZ7F3q3X9hjzbflss/UBeDYgmoxoiiP/3qwOFZ
97axCJ2etCdUyulg7+NuhfW/K6ZOO1oCJXPN+0sdAoGAFM9AUKTl5cDUVyJdQqN+
1eMgx4Z43rzCbYTub02TUhb3dRHZU65KWYx+On76FM60GJoE6aSAjhgIbWsCuzJe
JlsdG+fb/5bxBvabuSXXEu2FQXYnfUedtPbh2XmbsiJ9rrX0i3Rw61rXTibR/2OT
VWYQNxzU0QQjUdh1iP2EbM0CgYBwhbsPRVqJBjC8ZWP/tkI5gp73ccdmaHqbMLi6
zRMkkBtYydGpqXlq4KelvXEJ7vMXvpQGAA1YPGkXqoRPHoEWUw1lBbIuL5BZCNhO
WHXoOGsQ4h5redRaPv20EPRHmJyyoEeUnIUnBtFvFPMlDrKO5zZfYPZPbV8Vm+Dj
OMcV6QKBgQCn6mZu7UVqi2mcHLLEeodtCWt/EZzeMM3L0gFrUaD5BYlmGr9SKszh
j6seuchs/iBjrXOXNgS+2mzJU7wOK/qkjyHkfN88wCzpdJ9/wv08MdXzytM6OJEJ
WDW0HIiUR3ooJL1ZIaKWw+xlRBH6DX9c5XV0JM7zwv0qIIJXglnG8w==
-----END RSA PRIVATE KEY-----"""
    
    print("🚀 Initializing Kalshi client with official SDK...")
    
    # Initialize the official Kalshi client
    try:
        # Create configuration
        configuration = kalshi_python.Configuration()
        configuration.host = "https://api.elections.kalshi.com/trade-api/v2"
        
        # Create API client
        api_client = kalshi_python.ApiClient(configuration)
        
        # Create API instances for different endpoints
        exchange_api = kalshi_python.ExchangeApi(api_client)
        market_api = kalshi_python.MarketApi(api_client)
        auth_api = kalshi_python.AuthApi(api_client)
        
        print("✅ Official Kalshi SDK initialized")
        
        # Search for general temperature/weather markets
        weather_data = search_temperature_markets(exchange_api)
        
        if weather_data["events"]:
            print(f"\n📊 WEATHER MARKETS FOUND:")
            for event in weather_data["events"][:5]:
                print(f"  {event.get('event_ticker')} - {event.get('title')}")
        
        # Specifically search for NHIGH
        nhigh_data = search_for_nhigh_specifically(exchange_api)
        
        if nhigh_data["events"]:
            print(f"\n🎯 NHIGH MARKETS FOUND:")
            for event in nhigh_data["events"]:
                print(f"  {event.get('event_ticker')} - {event.get('title')}")
                
            # Analyze the historical data
            historical_df = analyze_historical_data(nhigh_data["markets"])
            
            if not historical_df.empty:
                print(f"\n💾 Saving {len(historical_df)} historical results...")
                historical_df.to_csv('kalshi_nhigh_official_sdk.csv', index=False)
                
                # Show sample of historical data
                settled_markets = historical_df[historical_df['status'].isin(['settled', 'closed', 'finalized'])]
                if not settled_markets.empty:
                    print("\n📈 Sample historical betting results:")
                    print(settled_markets[['market_ticker', 'subtitle', 'result', 'last_price']].head())
                else:
                    print("\n📈 Current active markets (no historical results yet):")
                    print(historical_df[['market_ticker', 'subtitle', 'status', 'last_price']].head())
            
        else:
            print("\n❌ No NHIGH (NYC High temperature) markets found")
            print("   NYC daily temperature betting is not currently available on Kalshi")
        
        # Save all weather-related data
        if weather_data["markets"]:
            all_weather_df = analyze_historical_data(weather_data["markets"])
            if not all_weather_df.empty:
                all_weather_df.to_csv('kalshi_weather_markets_official_sdk.csv', index=False)
                print(f"\n💾 Saved {len(all_weather_df)} weather-related markets to CSV")
        
    except Exception as e:
        print(f"❌ Error with official SDK: {e}")
        print("   This might be due to authentication or API changes")


if __name__ == "__main__":
    main()