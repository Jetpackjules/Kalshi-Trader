#!/usr/bin/env python3
"""
Quick test script to verify the Kalshi Market Viewer website
"""

import requests
import time

def test_website():
    url = "http://localhost:8080/kalshi_market_viewer.html"
    
    try:
        print("Testing website accessibility...")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            print("✅ Website is accessible!")
            print(f"   Content length: {len(response.text)} chars")
            
            # Check for key components
            content = response.text.lower()
            
            checks = [
                ("plotly library", "plotly" in content),
                ("chart container", "chartdiv" in content),
                ("date selector", "dateselect" in content),
                ("load button", "loadmarketdata" in content),
                ("kalshi title", "kalshi" in content and "market" in content)
            ]
            
            print("\n🔍 Component checks:")
            for name, passed in checks:
                status = "✅" if passed else "❌"
                print(f"   {status} {name}")
                
            return True
        else:
            print(f"❌ Website returned status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to website: {e}")
        return False

def test_data_files():
    print("\n📁 Checking data files:")
    
    import os
    files_to_check = [
        "data/candles/KXHIGHNY_candles_5m.csv",
        "kxhighny_markets_history.csv"
    ]
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            print(f"   ✅ {file_path} ({size:,} bytes)")
        else:
            print(f"   ❌ {file_path} (missing)")

if __name__ == "__main__":
    print("🌡️ Kalshi Market Viewer Test")
    print("=" * 40)
    
    # Give server a moment to start
    time.sleep(2)
    
    test_data_files()
    test_website()
    
    print("\n🎯 Instructions:")
    print("   1. Open http://localhost:8080/kalshi_market_viewer.html in your browser")
    print("   2. Select a date from the dropdown")
    print("   3. Click 'Load Market Data' to view trendlines")
    print("   4. Use the chart controls to zoom and explore")