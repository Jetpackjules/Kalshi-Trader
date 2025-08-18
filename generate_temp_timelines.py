#!/usr/bin/env python3
"""
Generate temperature timeline data (hourly) for all market dates
"""

import json
import sys
import os
from datetime import datetime, timedelta
import pandas as pd

# Add modules directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

try:
    from modules.synoptic_api import SynopticAPI  
    from modules.ncei_asos import NCEIASOS
except ImportError as e:
    print(f"Error importing weather APIs: {e}")
    sys.exit(1)

def get_market_dates():
    """Extract unique dates from candlestick data"""
    try:
        df = pd.read_csv('data/candles/KXHIGHNY_candles_5m.csv')
        dates = set()
        
        for ticker in df['ticker'].unique():
            # Extract date from ticker like KXHIGHNY-25AUG11-B88.5
            match = ticker.split('-')[1] if '-' in ticker else None
            if match:
                # Convert 25AUG11 to 2025-08-11
                try:
                    year = '20' + match[:2]
                    month_map = {
                        'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                        'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                        'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
                    }
                    month = month_map.get(match[2:5])
                    day = match[5:7]
                    if month:
                        date_str = f"{year}-{month}-{day}"
                        dates.add(date_str)
                except:
                    continue
        
        return sorted(list(dates))
    except Exception as e:
        print(f"Error reading market dates: {e}")
        return []

def fetch_temperature_timeline(date_str, api_name, api_instance):
    """Fetch hourly temperature timeline for a specific date and API"""
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get the detailed data with all observations
        result = api_instance.get_daily_max_temperature(target_date)
        
        if not result.get('success'):
            return {
                'success': False,
                'api': api_name,
                'date': date_str,
                'error': result.get('error', 'Unknown error'),
                'timeline': []
            }
        
        # Now get the raw observations for timeline
        timeline = []
        
        if hasattr(api_instance, 'last_observations') and api_instance.last_observations:
            for obs in api_instance.last_observations:
                try:
                    # Convert timestamp to string
                    timestamp = obs.get('timestamp')
                    if hasattr(timestamp, 'isoformat'):
                        timestamp_str = timestamp.isoformat()
                    elif hasattr(timestamp, 'strftime'):
                        timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%S')
                    else:
                        timestamp_str = str(timestamp)
                    
                    timeline.append({
                        'timestamp': timestamp_str,
                        'temperature': obs.get('temperature', 0),
                        'source': obs.get('source', api_name)
                    })
                except Exception as e:
                    print(f"Error processing observation: {e}")
                    continue
        
        # Sort by timestamp
        timeline.sort(key=lambda x: x['timestamp'])
        
        return {
            'success': True,
            'api': api_name,
            'date': date_str,
            'max_temperature': result.get('max_temperature'),
            'max_time': str(result.get('max_time')) if result.get('max_time') else None,
            'observation_count': len(timeline),
            'timeline': timeline,
            'source': result.get('source', f'{api_name.upper()} API')
        }
        
    except Exception as e:
        return {
            'success': False,
            'api': api_name,
            'date': date_str,
            'error': str(e),
            'timeline': []
        }

def main():
    print("🌡️ Generating temperature timeline data...")
    
    # Get all market dates
    market_dates = get_market_dates()
    print(f"Found {len(market_dates)} market dates: {market_dates[:5]}{'...' if len(market_dates) > 5 else ''}")
    
    # Initialize APIs
    apis = {
        'synoptic': SynopticAPI(),
        'asos': NCEIASOS()
    }
    
    # Store all temperature timeline data
    temperature_timelines = {}
    
    total_requests = len(market_dates) * len(apis)
    current_request = 0
    
    for date_str in market_dates:
        temperature_timelines[date_str] = {}
        
        for api_name, api_instance in apis.items():
            current_request += 1
            print(f"[{current_request}/{total_requests}] Fetching {api_name} timeline for {date_str}...")
            
            temp_result = fetch_temperature_timeline(date_str, api_name, api_instance)
            temperature_timelines[date_str][api_name] = temp_result
            
            if temp_result['success']:
                max_temp = temp_result['max_temperature']
                timeline_points = len(temp_result['timeline'])
                print(f"  ✅ {api_name}: {max_temp}°F max, {timeline_points} timeline points")
            else:
                print(f"  ❌ {api_name}: {temp_result.get('error', 'Failed')}")
    
    # Save to JSON file
    output_file = 'temperature_timelines.json'
    with open(output_file, 'w') as f:
        json.dump(temperature_timelines, f, indent=2)
    
    print(f"\n✅ Temperature timeline data saved to {output_file}")
    
    # Print summary
    successful_apis = {}
    total_timeline_points = {}
    
    for date_str, date_data in temperature_timelines.items():
        for api_name, api_data in date_data.items():
            if api_data['success']:
                if api_name not in successful_apis:
                    successful_apis[api_name] = 0
                    total_timeline_points[api_name] = 0
                successful_apis[api_name] += 1
                total_timeline_points[api_name] += len(api_data.get('timeline', []))
    
    print("\n📊 API Timeline Summary:")
    for api_name in successful_apis:
        success_count = successful_apis[api_name]
        timeline_count = total_timeline_points[api_name]
        success_rate = (success_count / len(market_dates)) * 100
        avg_points = timeline_count / success_count if success_count > 0 else 0
        print(f"  {api_name}: {success_count}/{len(market_dates)} dates ({success_rate:.1f}%), avg {avg_points:.1f} points/day")

if __name__ == '__main__':
    main()