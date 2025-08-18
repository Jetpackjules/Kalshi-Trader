#!/usr/bin/env python3
"""
Get winning market data for August 5th, 2025
"""
import sys
from datetime import datetime
sys.path.append('BACKLOG!')
from kalshi_temp_backtest import KalshiClient

def test_aug5_winner():
    print("🔍 Finding winning market for August 5th, 2025...")
    
    client = KalshiClient()
    
    # Get all KXHIGHNY markets
    print("📊 Fetching all KXHIGHNY markets...")
    all_markets = client.list_markets_by_series('KXHIGHNY', limit=2000)
    
    # Look for August 5th markets (25AUG05 format)
    target_date = "25AUG05"
    aug5_markets = []
    
    for market in all_markets:
        ticker = market.get('ticker', '')
        if target_date in ticker:
            aug5_markets.append(market)
    
    print(f"\n🎯 Found {len(aug5_markets)} markets for August 5th, 2025:")
    
    winner = None
    for market in aug5_markets:
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
        
        # Check if this is the winner
        if result == 'yes' or settlement == 100:
            winner = market
            print("     🏆 WINNER!")
        
        print()
    
    if winner:
        print(f"🏆 WINNING MARKET FOR AUGUST 5TH:")
        print(f"   Ticker: {winner.get('ticker')}")
        print(f"   Title: {winner.get('title')}")
        print(f"   Result: {winner.get('result')}")
        print(f"   Settlement: {winner.get('settlement_value')}")
        
        # Try to get historical data for the winner
        print(f"\n📊 Attempting to fetch historical data for winner...")
        try:
            market_id = winner.get('id') or winner.get('ticker')
            points = client.get_market_history_cached(str(market_id))
            print(f"   -> Got {len(points) if points else 0} historical data points")
            
            if points and len(points) > 0:
                print(f"   📈 Sample price data (last 5 points):")
                last_points = points[-5:] if len(points) >= 5 else points
                for p in last_points:
                    ts = p.get('ts', 'N/A')
                    price = p.get('last_price', p.get('price', 'N/A'))
                    print(f"      {ts}: ${price}")
            else:
                print("   ❌ No historical price data available")
                
        except Exception as e:
            print(f"   ❌ Error fetching historical data: {e}")
    else:
        print("❌ No winning market found for August 5th")

if __name__ == '__main__':
    test_aug5_winner()