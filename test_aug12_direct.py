#!/usr/bin/env python3
"""
Direct test of August 12th Kalshi data using the working backtest client
"""
import sys
from datetime import datetime
sys.path.append('BACKLOG!')
from kalshi_temp_backtest import KalshiClient

def test_aug12_markets():
    print("🔍 Testing August 12th Kalshi markets...")
    
    client = KalshiClient()
    
    # Get all KXHIGHNY markets
    print("📊 Fetching all KXHIGHNY markets...")
    all_markets = client.list_markets_by_series('KXHIGHNY', limit=2000)
    print(f"Found {len(all_markets)} total KXHIGHNY markets")
    
    # Look for August 12th markets (25AUG12 format)
    target_date = "25AUG12"
    aug12_markets = []
    
    for market in all_markets:
        ticker = market.get('ticker', '')
        if target_date in ticker:
            aug12_markets.append(market)
    
    print(f"\n🎯 Found {len(aug12_markets)} markets for August 12th, 2025:")
    
    for market in aug12_markets:
        ticker = market.get('ticker', 'N/A')
        status = market.get('status', 'unknown')
        result = market.get('result', 'N/A')
        settlement = market.get('settlement_value', 'N/A')
        title = market.get('title', 'N/A')
        
        print(f"  📈 {ticker}")
        print(f"     Status: {status}")
        print(f"     Result: {result}")
        print(f"     Settlement: {settlement}")
        print(f"     Title: {title}")
        
        # Get some market history if available
        print(f"     Fetching history for {ticker}...")
        try:
            market_id = market.get('id') or ticker
            points = client.get_market_history_cached(str(market_id))
            print(f"     -> Got {len(points) if points else 0} data points")
            
            if points and len(points) > 0:
                # Show last few points
                last_points = points[-3:] if len(points) >= 3 else points
                for p in last_points:
                    ts = p.get('ts', 'N/A')
                    price = p.get('last_price', p.get('price', 'N/A'))
                    print(f"       {ts}: ${price}")
        except Exception as e:
            print(f"     -> Error: {e}")
        
        print()

if __name__ == '__main__':
    test_aug12_markets()