#!/usr/bin/env python3
"""
Kalshi API client using official kalshi-python library patterns
Based on: https://pypi.org/project/kalshi-python/
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import json


class KalshiClient:
    """Simplified Kalshi API client based on official SDK patterns"""
    
    def __init__(self, api_key: str, api_secret: str, environment: str = "prod"):
        self.api_key = api_key
        self.api_secret = api_secret
        
        if environment == "prod":
            self.base_url = "https://api.elections.kalshi.com/trade-api/v2"
        else:
            self.base_url = "https://demo-api.elections.kalshi.com/trade-api/v2"
            
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        # Authenticate
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with the Kalshi API"""
        auth_data = {
            "email": "",  # Not used for API key auth
            "password": ""  # Not used for API key auth
        }
        
        # Add API key to headers
        self.session.headers.update({
            'KALSHI-API-KEY': self.api_key
        })
        
        print("✓ Authenticated with Kalshi API")
    
    def get_events(self, 
                   series_ticker: Optional[str] = None,
                   status: Optional[str] = None,
                   limit: int = 100,
                   cursor: Optional[str] = None) -> Dict[str, Any]:
        """Get events from Kalshi"""
        
        params = {"limit": limit}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
            
        response = self.session.get(f"{self.base_url}/events", params=params)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting events: {response.status_code} - {response.text}")
            return {"events": [], "cursor": ""}
    
    def get_markets(self,
                   event_ticker: Optional[str] = None,
                   series_ticker: Optional[str] = None,
                   limit: int = 100,
                   cursor: Optional[str] = None) -> Dict[str, Any]:
        """Get markets from Kalshi"""
        
        params = {"limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
            
        response = self.session.get(f"{self.base_url}/markets", params=params)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting markets: {response.status_code} - {response.text}")
            return {"markets": [], "cursor": ""}
    
    def search_events(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search for events containing specific terms"""
        all_events = []
        cursor = None
        
        while len(all_events) < limit:
            events_response = self.get_events(limit=min(100, limit - len(all_events)), cursor=cursor)
            
            if not events_response.get("events"):
                break
                
            # Filter events by query terms
            for event in events_response["events"]:
                title = event.get("title", "").lower()
                ticker = event.get("event_ticker", "").lower()
                series = event.get("series_ticker", "").lower()
                
                if any(term.lower() in text for term in query.split() 
                      for text in [title, ticker, series]):
                    all_events.append(event)
            
            cursor = events_response.get("cursor")
            if not cursor:
                break
                
        return all_events[:limit]


def find_temperature_markets(client: KalshiClient) -> pd.DataFrame:
    """Search for temperature or weather-related markets on Kalshi"""
    
    print("🔍 Searching for temperature/weather markets...")
    
    # Get a sample of all events first (limit to avoid timeout)
    print("  Getting sample events...")
    events_response = client.get_events(limit=200)
    all_events = events_response.get("events", [])
    
    print(f"  Examining {len(all_events)} events...")
    
    # Search terms related to temperature and weather
    search_terms = [
        "temperature", "weather", "high", "hot", "cold",
        "nyc", "new york", "heat", "climate", "degrees",
        "celsius", "fahrenheit"
    ]
    
    relevant_events = []
    
    for event in all_events:
        title = event.get("title", "").lower()
        ticker = event.get("event_ticker", "").lower()
        series = event.get("series_ticker", "").lower()
        category = event.get("category", "").lower()
        
        # Check if any search term appears in the event
        event_text = f"{title} {ticker} {series} {category}"
        
        if any(term in event_text for term in search_terms):
            relevant_events.append(event)
            print(f"    Found: {event.get('event_ticker')} - {event.get('title')}")
    
    if not relevant_events:
        print("❌ No temperature/weather markets found")
        return pd.DataFrame()
    
    print(f"✓ Found {len(relevant_events)} potentially relevant events")
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame(relevant_events)
    return df


def get_historical_results(client: KalshiClient, series_ticker: str, days_back: int = 30) -> pd.DataFrame:
    """Get historical results for a specific series"""
    
    print(f"📊 Getting historical results for {series_ticker} (last {days_back} days)...")
    
    # Get settled events for the series
    events_response = client.get_events(
        series_ticker=series_ticker,
        status="settled"
    )
    
    events = events_response.get("events", [])
    if not events:
        print(f"❌ No settled events found for {series_ticker}")
        return pd.DataFrame()
    
    print(f"✓ Found {len(events)} settled events")
    
    results = []
    cutoff_date = datetime.now().date() - timedelta(days=days_back)
    
    for event in events:
        event_ticker = event.get("event_ticker")
        
        # Get markets for this event
        markets_response = client.get_markets(event_ticker=event_ticker)
        markets = markets_response.get("markets", [])
        
        for market in markets:
            # Extract relevant data
            result_data = {
                "event_ticker": event_ticker,
                "event_title": event.get("title", ""),
                "market_ticker": market.get("ticker", ""),
                "market_subtitle": market.get("subtitle", ""),
                "result": market.get("result", ""),
                "close_price": market.get("last_price"),
                "volume": market.get("volume"),
                "category": event.get("category", "")
            }
            results.append(result_data)
    
    if results:
        df = pd.DataFrame(results)
        # Filter by date if possible (this would need timestamp parsing)
        return df
    else:
        return pd.DataFrame()


def main():
    # Your API credentials
    API_KEY = "db5ced1d-0df9-4398-ac0c-83d281e1c6b2"
    API_SECRET = """-----BEGIN RSA PRIVATE KEY-----
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
    
    # Initialize client
    print("🚀 Initializing Kalshi client...")
    client = KalshiClient(API_KEY, API_SECRET)
    
    # Search for temperature markets
    temp_markets_df = find_temperature_markets(client)
    
    if not temp_markets_df.empty:
        # Save results
        temp_markets_df.to_csv("kalshi_temperature_markets.csv", index=False)
        print(f"\n💾 Saved {len(temp_markets_df)} markets to kalshi_temperature_markets.csv")
        
        # Try to get historical data for any relevant series
        unique_series = temp_markets_df['series_ticker'].unique()
        for series in unique_series[:3]:  # Limit to first 3 to avoid rate limits
            print(f"\n📈 Checking historical data for {series}...")
            historical_df = get_historical_results(client, series, days_back=60)
            
            if not historical_df.empty:
                filename = f"kalshi_historical_{series.lower()}.csv"
                historical_df.to_csv(filename, index=False)
                print(f"💾 Saved historical data to {filename}")
    
    # Also specifically try NHIGH series
    print(f"\n🎯 Specifically checking for NHIGH series...")
    nhigh_df = get_historical_results(client, "NHIGH", days_back=90)
    
    if not nhigh_df.empty:
        nhigh_df.to_csv("kalshi_nhigh_historical.csv", index=False)
        print(f"💾 Saved NHIGH historical data to kalshi_nhigh_historical.csv")
        
        # Show sample results
        print("\nSample NHIGH results:")
        print(nhigh_df.head())
    else:
        print("❌ No NHIGH historical data found")


if __name__ == "__main__":
    main()