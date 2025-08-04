#!/usr/bin/env python3
"""
NYC Temperature Betting History - KXHIGHNY Series
Specifically searches for KXHIGHNY series using official Kalshi Python SDK
"""

import kalshi_python
import pandas as pd
from datetime import datetime, timedelta
import json


def search_kxhighny_markets(market_api) -> dict:
    """Search specifically for KXHIGHNY series markets"""
    
    print("🎯 Searching for KXHIGHNY (NYC High Temperature) markets...")
    
    # Search for events with KXHIGHNY series
    try:
        print("  Getting events for KXHIGHNY series...")
        events_response = market_api.get_events(series_ticker="KXHIGHNY")
        events = events_response.events if hasattr(events_response, 'events') else []
        
        if events:
            print(f"✅ Found {len(events)} KXHIGHNY events!")
            
            all_markets = []
            for event in events:
                try:
                    # Get event ticker properly
                    event_ticker = event.event_ticker if hasattr(event, 'event_ticker') else str(event)
                    print(f"  Processing event: {event_ticker}")
                    
                    # Get markets for this event
                    markets_response = market_api.get_markets(event_ticker=event_ticker)
                    markets = markets_response.markets if hasattr(markets_response, 'markets') else []
                    
                    print(f"    Found {len(markets)} markets for {event_ticker}")
                    
                    for market in markets:
                        # Convert market to dict for easier handling
                        market_data = {
                            'event_ticker': event_ticker,
                            'event_title': event.title if hasattr(event, 'title') else 'N/A',
                            'market_ticker': market.ticker if hasattr(market, 'ticker') else 'N/A',
                            'subtitle': market.subtitle if hasattr(market, 'subtitle') else 'N/A',
                            'status': market.status if hasattr(market, 'status') else 'N/A',
                            'result': market.result if hasattr(market, 'result') else 'N/A',
                            'last_price': market.last_price if hasattr(market, 'last_price') else None,
                            'volume': market.volume if hasattr(market, 'volume') else 0,
                            'close_time': market.close_time if hasattr(market, 'close_time') else 'N/A',
                            'category': event.category if hasattr(event, 'category') else 'N/A'
                        }
                        all_markets.append(market_data)
                        
                        # Print market details
                        print(f"      Market: {market_data['subtitle']} [{market_data['status']}] - Price: {market_data['last_price']}")
                        if market_data['result'] and market_data['result'] != 'N/A':
                            print(f"        Result: {market_data['result']}")
                    
                except Exception as e:
                    print(f"    Error getting markets for event: {e}")
            
            return {"events": events, "markets": all_markets}
        else:
            print("❌ No KXHIGHNY events found")
            return {"events": [], "markets": []}
            
    except Exception as e:
        print(f"❌ Error searching for KXHIGHNY: {e}")
        return {"events": [], "markets": []}


def analyze_kxhighny_results(markets) -> pd.DataFrame:
    """Analyze KXHIGHNY market results"""
    
    if not markets:
        print("❌ No markets to analyze")
        return pd.DataFrame()
    
    print(f"📊 Analyzing {len(markets)} KXHIGHNY markets...")
    
    df = pd.DataFrame(markets)
    
    # Show summary statistics
    print(f"\n📈 KXHIGHNY Market Summary:")
    print(f"  Total markets: {len(df)}")
    
    if 'status' in df.columns:
        status_counts = df['status'].value_counts()
        print(f"  Status breakdown: {dict(status_counts)}")
    
    # Filter for settled/closed markets (historical results)
    settled_markets = df[df['status'].isin(['settled', 'closed', 'finalized'])]
    if not settled_markets.empty:
        print(f"  Historical results available: {len(settled_markets)} settled markets")
        
        # Show settled markets with results
        results = settled_markets[settled_markets['result'].notna() & (settled_markets['result'] != 'N/A')]
        if not results.empty:
            print(f"\n🏆 Historical Betting Results:")
            for _, row in results.iterrows():
                print(f"    {row['subtitle']}: {row['result']} (Final price: {row['last_price']})")
    
    # Show active markets
    active_markets = df[df['status'] == 'active']
    if not active_markets.empty:
        print(f"  Current active markets: {len(active_markets)}")
        print(f"\n📊 Current Active Markets:")
        for _, row in active_markets.head(10).iterrows():
            print(f"    {row['subtitle']}: ${row['last_price']/100:.2f}" if row['last_price'] else f"    {row['subtitle']}: No price")
    
    return df


def main():
    # Your API credentials
    API_KEY_ID = "db5ced1d-0df9-4398-ac0c-83d281e1c6b2"
    
    print("🚀 Initializing Kalshi client for KXHIGHNY search...")
    
    try:
        # Create configuration
        configuration = kalshi_python.Configuration()
        configuration.host = "https://api.elections.kalshi.com/trade-api/v2"
        
        # Create API client and market API
        api_client = kalshi_python.ApiClient(configuration)
        market_api = kalshi_python.MarketApi(api_client)
        
        # Set API key in headers
        api_client.default_headers['KALSHI-API-KEY'] = API_KEY_ID
        
        print("✅ Kalshi SDK initialized")
        
        # Search specifically for KXHIGHNY
        kxhighny_data = search_kxhighny_markets(market_api)
        
        if kxhighny_data["events"]:
            print(f"\n🎯 SUCCESS: Found KXHIGHNY markets!")
            
            # Analyze the results
            df = analyze_kxhighny_results(kxhighny_data["markets"])
            
            if not df.empty:
                # Save to CSV
                filename = 'kxhighny_markets_history.csv'
                df.to_csv(filename, index=False)
                print(f"\n💾 Saved {len(df)} markets to {filename}")
                
                # Show sample data
                print(f"\n📋 Sample data:")
                display_cols = ['event_ticker', 'subtitle', 'status', 'result', 'last_price']
                available_cols = [col for col in display_cols if col in df.columns]
                print(df[available_cols].head(10).to_string(index=False))
            
        else:
            print(f"\n❌ No KXHIGHNY markets found on Kalshi")
            print("   NYC daily temperature betting may not be currently available")
            
            # Let's also try a broader search to see what's available
            print(f"\n🔍 Let's check what series are available with 'HIGH' in the name...")
            try:
                all_events = market_api.get_events(limit=1000)
                events = all_events.events if hasattr(all_events, 'events') else []
                
                high_series = set()
                ny_series = set()
                
                for event in events:
                    series = event.series_ticker if hasattr(event, 'series_ticker') else ''
                    if 'HIGH' in series.upper():
                        high_series.add(series)
                    if 'NY' in series.upper() or 'YORK' in series.upper():
                        ny_series.add(series)
                
                if high_series:
                    print(f"  Series with 'HIGH': {sorted(high_series)}")
                if ny_series:
                    print(f"  Series with 'NY': {sorted(ny_series)}")
                    
            except Exception as e:
                print(f"  Error in broader search: {e}")
    
    except Exception as e:
        print(f"❌ Error initializing Kalshi SDK: {e}")


if __name__ == "__main__":
    main()