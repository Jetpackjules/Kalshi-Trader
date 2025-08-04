#!/usr/bin/env python3
"""
Analyze KXHIGHNY historical betting results
"""

import pandas as pd
import numpy as np
from datetime import datetime
import re


def parse_date_from_ticker(ticker):
    """Parse date from event ticker like KXHIGHNY-25AUG04"""
    match = re.search(r'(\d{2})([A-Z]{3})(\d{2})', ticker)
    if match:
        year, month_str, day = match.groups()
        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        if month_str in month_map:
            return datetime(2000 + int(year), month_map[month_str], int(day)).date()
    return None


def extract_temperature_from_subtitle(subtitle):
    """Extract temperature from subtitle like '86° to 87°' or '85° or below'"""
    if '° to ' in subtitle:
        # Range like "86° to 87°"
        temps = re.findall(r'(\d+)°', subtitle)
        if len(temps) == 2:
            return (int(temps[0]) + int(temps[1])) / 2
    elif '° or above' in subtitle:
        # "85° or above"
        temp = re.search(r'(\d+)° or above', subtitle)
        if temp:
            return int(temp.group(1)) + 2  # Approximate center
    elif '° or below' in subtitle:
        # "85° or below"
        temp = re.search(r'(\d+)° or below', subtitle)
        if temp:
            return int(temp.group(1)) - 2  # Approximate center
    return None


def main():
    print("🔍 Analyzing KXHIGHNY historical betting results...")
    
    # Load the data
    df = pd.read_csv('kxhighny_markets_history.csv')
    print(f"📊 Loaded {len(df)} market records")
    
    # Parse dates
    df['date'] = df['event_ticker'].apply(parse_date_from_ticker)
    df = df.dropna(subset=['date'])
    
    # Extract temperatures
    df['temp_center'] = df['subtitle'].apply(extract_temperature_from_subtitle)
    
    # Focus on settled markets with results
    settled = df[df['status'] == 'finalized'].copy()
    print(f"📈 Found {len(settled)} finalized markets")
    
    # Find winning temperatures by date
    winners = settled[settled['result'] == 'yes'].copy()
    print(f"🏆 Found {len(winners)} winning bets")
    
    if not winners.empty:
        print(f"\n📋 Historical NYC Temperature Results:")
        print(f"Date Range: {winners['date'].min()} to {winners['date'].max()}")
        
        # Show winning temperatures by date
        daily_winners = winners.groupby('date').agg({
            'subtitle': 'first',
            'temp_center': 'first',
            'last_price': 'first',
            'volume': 'first'
        }).sort_values('date', ascending=False)
        
        print(f"\n🌡️ Recent Winning Temperatures:")
        for date, row in daily_winners.head(20).iterrows():
            temp_display = f"{row['temp_center']:.0f}°F" if pd.notna(row['temp_center']) else "N/A"
            print(f"  {date}: {row['subtitle']} ({temp_display}) - Final Price: {row['last_price']}¢")
        
        # Temperature statistics
        valid_temps = daily_winners['temp_center'].dropna()
        if not valid_temps.empty:
            print(f"\n📊 Temperature Statistics:")
            print(f"  Average temperature: {valid_temps.mean():.1f}°F")
            print(f"  Median temperature: {valid_temps.median():.1f}°F")
            print(f"  Min temperature: {valid_temps.min():.1f}°F")
            print(f"  Max temperature: {valid_temps.max():.1f}°F")
            print(f"  Standard deviation: {valid_temps.std():.1f}°F")
        
        # Market efficiency analysis
        print(f"\n💰 Market Efficiency Analysis:")
        
        # Count how many markets closed at extreme prices (1¢ or 99¢)
        extreme_prices = settled[settled['last_price'].isin([1, 99])]
        total_settled = len(settled)
        print(f"  Markets with extreme prices (1¢ or 99¢): {len(extreme_prices)}/{total_settled} ({len(extreme_prices)/total_settled*100:.1f}%)")
        
        # Volume analysis
        print(f"  Average trading volume: {settled['volume'].mean():.0f}")
        print(f"  Total volume traded: ${settled['volume'].sum():,}")
        
        # Show most active markets
        high_volume = settled.nlargest(10, 'volume')
        print(f"\n📈 Highest Volume Markets:")
        for _, row in high_volume.iterrows():
            date = row['date']
            subtitle = row['subtitle']
            volume = row['volume']
            result = row['result']
            print(f"  {date}: {subtitle} - Volume: {volume:,} ({'✅' if result == 'yes' else '❌'})")
        
        # Save analysis
        daily_winners.to_csv('kxhighny_daily_results.csv')
        print(f"\n💾 Saved daily results to kxhighny_daily_results.csv")
        
        # Show market structure
        print(f"\n🎯 Market Structure Analysis:")
        sample_event = df[df['event_ticker'] == df['event_ticker'].iloc[0]]
        print(f"  Markets per day: {len(sample_event)}")
        print(f"  Temperature ranges offered:")
        for _, row in sample_event.iterrows():
            print(f"    {row['subtitle']}")
    
    else:
        print("❌ No winning bets found in the data")


if __name__ == "__main__":
    main()