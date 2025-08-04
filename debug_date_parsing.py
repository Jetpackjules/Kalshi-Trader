#!/usr/bin/env python3
"""Debug date parsing issue"""

import pandas as pd

def debug_date_parsing():
    print("🔧 DEBUG: Date Parsing")
    
    # Test the actual parsing logic
    date_str = "07/30/25"
    
    year_part = f"20{date_str.split('/')[-1]}"
    month_day_part = '/'.join(date_str.split('/')[:2])
    full_date_str = f"{month_day_part}/{year_part}"
    
    print(f"🔍 Original date: {date_str}")
    print(f"🔍 Year part: {year_part}")
    print(f"🔍 Month/day part: {month_day_part}")
    print(f"🔍 Full date string: {full_date_str}")
    
    datetime_str = f"{full_date_str} 00:00:31"
    print(f"🔍 Full datetime string: {datetime_str}")
    
    timestamp_utc = pd.to_datetime(datetime_str, format='%m/%d/%Y %H:%M:%S', errors='coerce')
    print(f"🔍 Parsed timestamp: {timestamp_utc}")
    
    # Check if the issue is with pandas interpretation
    alt_timestamp = pd.to_datetime(datetime_str, errors='coerce')
    print(f"🔍 Alternative parsing: {alt_timestamp}")

if __name__ == "__main__":
    debug_date_parsing()