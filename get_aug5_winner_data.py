#!/usr/bin/env python3
"""
Get ALL timestamp data for the Aug 5th winning market KXHIGHNY-25AUG05-B85.5
"""
import sys
from datetime import datetime
sys.path.append('BACKLOG!')
from kalshi_temp_backtest import KalshiClient, fetch_public_trades_elections_v1

def get_aug5_winner_full_data():
    print("🔍 Getting ALL timestamp data for Aug 5th winner: KXHIGHNY-25AUG05-B85.5")
    
    client = KalshiClient()
    winner_ticker = "KXHIGHNY-25AUG05-B85.5"
    
    print(f"\n📊 Attempting multiple data sources for {winner_ticker}...")
    
    # Try to get market UUID first
    market_uuid = None
    try:
        print("🔍 Resolving ticker to market UUID...")
        r = client.session.get(
            f"https://api.elections.kalshi.com/v1/markets_by_ticker/{winner_ticker}",
            timeout=client.timeout_s,
        )
        if r.status_code < 400:
            market_data = r.json()
            market_uuid = market_data.get("market", {}).get("id")
            print(f"✅ Resolved to UUID: {market_uuid}")
            
            # Print all available market info
            market_info = market_data.get("market", {})
            print(f"\n📋 Market Information:")
            for key, value in market_info.items():
                print(f"   {key}: {value}")
        else:
            print(f"❌ UUID resolution failed: {r.status_code}")
    except Exception as e:
        print(f"❌ UUID resolution error: {e}")
    
    # Try multiple endpoints for historical data
    all_data_points = []
    
    if market_uuid:
        # 1. Try cached stats history (elections v1)
        print(f"\n🔍 Trying cached stats history (elections v1)...")
        try:
            r = client.session.get(f"https://api.elections.kalshi.com/v1/cached/markets/{market_uuid}/stats_history", timeout=15)
            if r.status_code < 400:
                data = r.json()
                points = []
                if isinstance(data, list):
                    points = data
                elif data.get('points'):
                    points = data['points']
                elif data.get('stats'):
                    points = data['stats']
                    
                print(f"   ✅ Got {len(points)} points from cached stats")
                all_data_points.extend(points)
                
                # Show sample data
                if points:
                    print("   📈 Sample cached stats data:")
                    for i, p in enumerate(points[:3]):
                        print(f"      Point {i+1}: {p}")
            else:
                print(f"   ❌ Cached stats failed: {r.status_code}")
        except Exception as e:
            print(f"   ❌ Cached stats error: {e}")
        
        # 2. Try regular stats history (elections v1)
        print(f"\n🔍 Trying regular stats history (elections v1)...")
        try:
            r = client.session.get(f"https://api.elections.kalshi.com/v1/markets/{market_uuid}/stats_history", timeout=15)
            if r.status_code < 400:
                data = r.json()
                points = []
                if isinstance(data, list):
                    points = data
                elif data.get('points'):
                    points = data['points']
                elif data.get('stats'):
                    points = data['stats']
                    
                print(f"   ✅ Got {len(points)} points from regular stats")
                all_data_points.extend(points)
                
                if points:
                    print("   📈 Sample regular stats data:")
                    for i, p in enumerate(points[:3]):
                        print(f"      Point {i+1}: {p}")
            else:
                print(f"   ❌ Regular stats failed: {r.status_code}")
        except Exception as e:
            print(f"   ❌ Regular stats error: {e}")
        
        # 3. Try trades data (elections v1)
        print(f"\n🔍 Trying trades data (elections v1)...")
        try:
            trades = fetch_public_trades_elections_v1(client.session, market_uuid, limit=1000)
            print(f"   ✅ Got {len(trades)} trades from elections v1")
            
            if trades:
                print("   💰 Sample trades data:")
                for i, trade in enumerate(trades[:5]):
                    print(f"      Trade {i+1}: {trade}")
                
                # Convert trades to timestamp format
                trade_points = []
                for trade in trades:
                    if trade.get('create_date') and trade.get('price'):
                        trade_points.append({
                            'timestamp': trade['create_date'],
                            'ts': trade['create_date'],
                            'price': float(trade['price']),
                            'last_price': float(trade['price']),
                            'source': 'trade'
                        })
                
                all_data_points.extend(trade_points)
                print(f"   📊 Converted {len(trade_points)} trades to timestamp points")
                
        except Exception as e:
            print(f"   ❌ Trades error: {e}")
    
    # 4. Try with ticker as market_id 
    print(f"\n🔍 Trying direct ticker access...")
    try:
        points = client.get_market_history_cached(winner_ticker)
        print(f"   ✅ Got {len(points)} points from direct ticker access")
        all_data_points.extend(points)
    except Exception as e:
        print(f"   ❌ Direct ticker error: {e}")
    
    # Remove duplicates and sort by timestamp
    print(f"\n📊 Processing {len(all_data_points)} total data points...")
    
    if all_data_points:
        # Deduplicate based on timestamp
        unique_points = {}
        for point in all_data_points:
            ts_key = point.get('ts') or point.get('timestamp') or point.get('create_date')
            if ts_key:
                unique_points[ts_key] = point
        
        sorted_points = sorted(unique_points.values(), key=lambda x: x.get('ts') or x.get('timestamp') or x.get('create_date') or '')
        
        print(f"✅ Final dataset: {len(sorted_points)} unique timestamped data points")
        
        print(f"\n📈 ALL TIMESTAMP DATA FOR {winner_ticker}:")
        print("=" * 80)
        
        for i, point in enumerate(sorted_points, 1):
            timestamp = point.get('ts') or point.get('timestamp') or point.get('create_date')
            price = point.get('last_price') or point.get('price') or point.get('forecast') or 'N/A'
            source = point.get('source', 'stats')
            
            # Try to parse timestamp for better display
            try:
                if isinstance(timestamp, str):
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                else:
                    formatted_time = str(timestamp)
            except:
                formatted_time = str(timestamp)
            
            print(f"{i:3d}. {formatted_time} | Price: ${price} | Source: {source}")
            
            # Show additional fields if available
            other_fields = {k: v for k, v in point.items() if k not in ['ts', 'timestamp', 'create_date', 'last_price', 'price', 'source']}
            if other_fields:
                print(f"     Extra data: {other_fields}")
        
        print("=" * 80)
        print(f"🎯 Total data points with timestamps: {len(sorted_points)}")
        
        # Show price range
        prices = [float(p.get('last_price') or p.get('price') or 0) for p in sorted_points if p.get('last_price') or p.get('price')]
        if prices:
            print(f"💰 Price range: ${min(prices):.3f} - ${max(prices):.3f}")
            print(f"📊 Final price: ${prices[-1]:.3f}")
    
    else:
        print("❌ No timestamp data found for this market")

if __name__ == '__main__':
    get_aug5_winner_full_data()