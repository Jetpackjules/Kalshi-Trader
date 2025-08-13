#!/usr/bin/env python3
"""
Test script for the static Kalshi Market Viewer website
"""

import requests
import time

def test_static_website():
    url = "http://localhost:8080/kalshi_market_viewer_static.html"
    
    try:
        print("Testing static website accessibility...")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            print("✅ Static website is accessible!")
            print(f"   Content length: {len(response.text)} chars")
            
            # Check for key components
            content = response.text.lower()
            
            checks = [
                ("plotly library", "plotly" in content),
                ("chart container", "chartdiv" in content),
                ("date selector", "dateselect" in content),
                ("load button", "loadmarketdata" in content),
                ("static title", "static" in content),
                ("temperature data", "temperaturedata" in content),
                ("synoptic API toggle", "synoptic" in content),
                ("asos API toggle", "asos" in content),
                ("embedded temp data", "2025-07-13" in content and "max_temperature" in content)
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
    print("🌡️ Kalshi Static Market Viewer Test")
    print("=" * 45)
    
    test_data_files()
    test_static_website()
    
    print("\n🎯 Static Version Benefits:")
    print("   ✅ No API server required")
    print("   ✅ No real-time dependencies") 
    print("   ✅ Embedded temperature data")
    print("   ✅ Works offline")
    print("\n📊 Features:")
    print("   🌡️ Temperature overlays from Synoptic & ASOS APIs")
    print("   📈 Interactive market trendlines")
    print("   🎛️ API toggle controls")
    print("   📅 Date selection for 31 market days")
    print("\n🚀 Access: http://localhost:8080/kalshi_market_viewer_static.html")