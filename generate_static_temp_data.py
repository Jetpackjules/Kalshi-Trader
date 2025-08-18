#!/usr/bin/env python3
"""
Generate static temperature data for all market dates
"""

import json
import sys
import os
from datetime import datetime, timedelta
import pandas as pd

# Add modules directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

try:
    from modules.nws_api import NWSAPI
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

def fetch_temperature_data(date_str, api_name, api_instance):
    """Fetch temperature data for a specific date and API"""
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        result = api_instance.get_daily_max_temperature(target_date)
        
        if result.get('success'):
            # Convert datetime to string if needed
            max_time = result.get('max_time')
            if hasattr(max_time, 'isoformat'):
                max_time = max_time.isoformat()
            elif hasattr(max_time, 'strftime'):
                max_time = max_time.strftime('%Y-%m-%d %H:%M:%S')
            
            return {
                'success': True,
                'api': api_name,
                'date': date_str,
                'max_temperature': result.get('max_temperature'),
                'max_time': str(max_time) if max_time else None,
                'observation_count': result.get('observation_count', 0),
                'source': result.get('source', f'{api_name.upper()} API')
            }
        else:
            return {
                'success': False,
                'api': api_name,
                'date': date_str,
                'error': result.get('error', 'Unknown error')
            }
    except Exception as e:
        return {
            'success': False,
            'api': api_name,
            'date': date_str,
            'error': str(e)
        }

def main():
    print("🌡️ Generating static temperature data...")
    
    # Get all market dates
    market_dates = get_market_dates()
    print(f"Found {len(market_dates)} market dates: {market_dates[:5]}{'...' if len(market_dates) > 5 else ''}")
    
    # Initialize APIs
    apis = {
        'nws': NWSAPI(),
        'synoptic': SynopticAPI(),
        'asos': NCEIASOS()
    }
    
    # Store all temperature data
    temperature_data = {}
    
    total_requests = len(market_dates) * len(apis)
    current_request = 0
    
    for date_str in market_dates:
        temperature_data[date_str] = {}
        
        for api_name, api_instance in apis.items():
            current_request += 1
            print(f"[{current_request}/{total_requests}] Fetching {api_name} data for {date_str}...")
            
            temp_result = fetch_temperature_data(date_str, api_name, api_instance)
            temperature_data[date_str][api_name] = temp_result
            
            if temp_result['success']:
                temp = temp_result['max_temperature']
                print(f"  ✅ {api_name}: {temp}°F")
            else:
                print(f"  ❌ {api_name}: {temp_result.get('error', 'Failed')}")
    
    # Save to JSON file
    output_file = 'static_temperature_data.json'
    with open(output_file, 'w') as f:
        json.dump(temperature_data, f, indent=2)
    
    print(f"\n✅ Static temperature data saved to {output_file}")
    
    # Print summary
    successful_apis = {}
    for date_str, date_data in temperature_data.items():
        for api_name, api_data in date_data.items():
            if api_data['success']:
                if api_name not in successful_apis:
                    successful_apis[api_name] = 0
                successful_apis[api_name] += 1
    
    print("\n📊 API Success Summary:")
    for api_name, success_count in successful_apis.items():
        success_rate = (success_count / len(market_dates)) * 100
        print(f"  {api_name}: {success_count}/{len(market_dates)} dates ({success_rate:.1f}%)")

if __name__ == '__main__':
    main()