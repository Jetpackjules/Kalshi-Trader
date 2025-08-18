#!/usr/bin/env python3
"""
Kalshi Price vs NWS Temperature Analysis
Compare actual Kalshi KXHIGHNY market pricing with official NWS settlement temperatures
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import json
import re
from pathlib import Path

# Import our modules
from modules.kalshi_nws_source import KalshiNWSSource

def load_kalshi_market_data() -> pd.DataFrame:
    """Load the Kalshi market data from the CSV we just created"""
    
    print("📊 Loading Kalshi KXHIGHNY market data...")
    
    try:
        df = pd.read_csv('kxhighny_markets_history.csv')
        print(f"✅ Loaded {len(df)} market records")
        
        # Show data structure
        print(f"\n📋 Data columns: {list(df.columns)}")
        print(f"📅 Date range: {df['event_ticker'].min()} to {df['event_ticker'].max()}")
        
        return df
        
    except FileNotFoundError:
        print("❌ Kalshi market data file not found. Please run the search first.")
        return pd.DataFrame()
    except Exception as e:
        print(f"❌ Error loading Kalshi data: {e}")
        return pd.DataFrame()

def extract_date_from_event_ticker(event_ticker: str) -> Optional[date]:
    """Extract date from KXHIGHNY event ticker format like KXHIGHNY-25JUL30"""
    
    try:
        # Pattern: KXHIGHNY-25JUL30
        match = re.match(r'KXHIGHNY-(\d{2})([A-Z]{3})(\d{2})', event_ticker)
        if not match:
            return None
            
        year_suffix, month_abbr, day = match.groups()
        
        # Convert to full year (25 -> 2025)
        year = 2000 + int(year_suffix)
        
        # Month abbreviation to number
        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        month = month_map.get(month_abbr)
        if not month:
            return None
            
        return date(year, month, int(day))
        
    except Exception as e:
        print(f"Error parsing date from {event_ticker}: {e}")
        return None

def extract_temperature_range_from_subtitle(subtitle: str) -> Dict:
    """Extract temperature range from market subtitle like '94° to 95°' or '85° or below'"""
    
    try:
        # Pattern 1: "X° to Y°" (range)
        range_match = re.match(r'(\d+)° to (\d+)°', subtitle)
        if range_match:
            low, high = map(int, range_match.groups())
            return {
                'type': 'range',
                'low': low,
                'high': high,
                'midpoint': (low + high) / 2
            }
        
        # Pattern 2: "X° or above" (upper tail)
        above_match = re.match(r'(\d+)° or above', subtitle)
        if above_match:
            threshold = int(above_match.group(1))
            return {
                'type': 'above',
                'threshold': threshold,
                'low': threshold,
                'high': threshold + 10,  # Estimate for visualization
                'midpoint': threshold + 5
            }
        
        # Pattern 3: "X° or below" (lower tail)
        below_match = re.match(r'(\d+)° or below', subtitle)
        if below_match:
            threshold = int(below_match.group(1))
            return {
                'type': 'below',
                'threshold': threshold,
                'low': threshold - 10,  # Estimate for visualization
                'high': threshold,
                'midpoint': threshold - 5
            }
        
        return {'type': 'unknown', 'midpoint': None}
        
    except Exception as e:
        print(f"Error parsing temperature from {subtitle}: {e}")
        return {'type': 'error', 'midpoint': None}

def get_nws_settlement_data(start_date: date, end_date: date) -> pd.DataFrame:
    """Get official NWS settlement temperatures for the date range"""
    
    print(f"🌡️ Fetching NWS settlement data from {start_date} to {end_date}...")
    
    nws_source = KalshiNWSSource("KNYC")
    results = []
    
    current_date = start_date
    while current_date <= end_date:
        try:
            result = nws_source.get_daily_max_temperature(current_date)
            
            if result.get('max_temp') is not None:
                results.append({
                    'date': current_date,
                    'nws_max_temp': result['max_temp'],
                    'nws_max_time': result.get('max_time', ''),
                    'nws_count': result.get('count', 0)
                })
                print(f"  ✅ {current_date}: {result['max_temp']}°F")
            else:
                print(f"  ❌ {current_date}: No NWS data - {result.get('error', 'Unknown error')}")
                results.append({
                    'date': current_date,
                    'nws_max_temp': None,
                    'nws_max_time': None,
                    'nws_count': 0
                })
                
        except Exception as e:
            print(f"  💥 {current_date}: Error - {e}")
            results.append({
                'date': current_date,
                'nws_max_temp': None,
                'nws_max_time': None,
                'nws_count': 0
            })
        
        current_date += timedelta(days=1)
    
    df = pd.DataFrame(results)
    print(f"✅ Retrieved NWS data for {len(df)} days")
    return df

def analyze_kalshi_vs_nws(kalshi_df: pd.DataFrame, nws_df: pd.DataFrame) -> pd.DataFrame:
    """Analyze Kalshi market predictions vs actual NWS temperatures"""
    
    print("🔍 Analyzing Kalshi predictions vs NWS actuals...")
    
    # Process Kalshi data
    kalshi_processed = []
    
    for _, row in kalshi_df.iterrows():
        event_date = extract_date_from_event_ticker(row['event_ticker'])
        if not event_date:
            continue
            
        temp_info = extract_temperature_range_from_subtitle(row['subtitle'])
        
        kalshi_processed.append({
            'date': event_date,
            'event_ticker': row['event_ticker'],
            'market_ticker': row['market_ticker'],
            'subtitle': row['subtitle'],
            'temp_type': temp_info['type'],
            'temp_low': temp_info.get('low'),
            'temp_high': temp_info.get('high'),
            'temp_midpoint': temp_info.get('midpoint'),
            'kalshi_price': row['last_price'],
            'kalshi_result': row['result'],
            'status': row['status']
        })
    
    kalshi_processed_df = pd.DataFrame(kalshi_processed)
    
    # Merge with NWS data
    merged_df = kalshi_processed_df.merge(nws_df, on='date', how='inner')
    
    # Filter for settled markets with results
    settled_df = merged_df[
        (merged_df['status'] == 'finalized') & 
        (merged_df['kalshi_result'].isin(['yes', 'no'])) &
        (merged_df['nws_max_temp'].notna())
    ].copy()
    
    # Add analysis columns
    settled_df['kalshi_price_pct'] = settled_df['kalshi_price'] / 100  # Convert cents to percentage
    settled_df['market_won'] = settled_df['kalshi_result'] == 'yes'
    
    # Determine if NWS temperature fell in the predicted range
    def temp_in_range(row):
        nws_temp = row['nws_max_temp']
        temp_type = row['temp_type']
        
        if temp_type == 'range':
            return row['temp_low'] <= nws_temp <= row['temp_high']
        elif temp_type == 'above':
            return nws_temp >= row['temp_low']
        elif temp_type == 'below':
            return nws_temp <= row['temp_high']
        else:
            return None
    
    settled_df['temp_in_predicted_range'] = settled_df.apply(temp_in_range, axis=1)
    settled_df['prediction_correct'] = settled_df['market_won'] == settled_df['temp_in_predicted_range']
    
    print(f"✅ Analysis complete: {len(settled_df)} settled markets with NWS data")
    
    return settled_df

def create_analysis_report(analysis_df: pd.DataFrame) -> None:
    """Create comprehensive analysis report"""
    
    print("\n" + "="*80)
    print("📊 KALSHI vs NWS TEMPERATURE ANALYSIS REPORT")
    print("="*80)
    
    total_markets = len(analysis_df)
    
    if total_markets == 0:
        print("❌ No data available for analysis")
        return
    
    # Basic statistics
    print(f"\n📈 OVERVIEW:")
    print(f"  Total settled markets analyzed: {total_markets}")
    print(f"  Date range: {analysis_df['date'].min()} to {analysis_df['date'].max()}")
    print(f"  Average market price: {analysis_df['kalshi_price_pct'].mean():.1%}")
    
    # Market accuracy
    correct_predictions = analysis_df['prediction_correct'].sum()
    accuracy = correct_predictions / total_markets
    print(f"\n🎯 MARKET PREDICTION ACCURACY:")
    print(f"  Correct predictions: {correct_predictions}/{total_markets} ({accuracy:.1%})")
    
    won_markets = analysis_df['market_won'].sum()
    win_rate = won_markets / total_markets
    print(f"  Markets that resolved 'Yes': {won_markets}/{total_markets} ({win_rate:.1%})")
    
    # Temperature analysis
    print(f"\n🌡️ TEMPERATURE ANALYSIS:")
    print(f"  NWS temperature range: {analysis_df['nws_max_temp'].min():.1f}°F to {analysis_df['nws_max_temp'].max():.1f}°F")
    print(f"  Average NWS temperature: {analysis_df['nws_max_temp'].mean():.1f}°F")
    print(f"  Temperature standard deviation: {analysis_df['nws_max_temp'].std():.1f}°F")
    
    # Price vs outcome analysis
    won_markets_df = analysis_df[analysis_df['market_won']]
    lost_markets_df = analysis_df[~analysis_df['market_won']]
    
    if len(won_markets_df) > 0 and len(lost_markets_df) > 0:
        print(f"\n💰 PRICE vs OUTCOME ANALYSIS:")
        print(f"  Average price of winning markets: ${won_markets_df['kalshi_price'].mean()/100:.2f}")
        print(f"  Average price of losing markets: ${lost_markets_df['kalshi_price'].mean()/100:.2f}")
    
    # Daily breakdown for recent days
    print(f"\n📅 RECENT DAILY RESULTS (Last 10 days):")
    recent_df = analysis_df.nlargest(10, 'date')
    
    for _, row in recent_df.iterrows():
        result_emoji = "✅" if row['market_won'] else "❌"
        accuracy_emoji = "🎯" if row['prediction_correct'] else "❗"
        print(f"  {row['date']} {result_emoji} {accuracy_emoji}: {row['subtitle']} → NWS: {row['nws_max_temp']:.1f}°F (${row['kalshi_price']/100:.2f})")

def create_simple_analysis_summary(analysis_df: pd.DataFrame) -> None:
    """Create a simple text-based summary without plotting"""
    
    print("\n📊 Creating analysis summary...")
    
    if len(analysis_df) == 0:
        print("❌ No data available for visualization")
        return
    
    # Temperature analysis
    temp_stats = {
        'min': analysis_df['nws_max_temp'].min(),
        'max': analysis_df['nws_max_temp'].max(),
        'mean': analysis_df['nws_max_temp'].mean(),
        'std': analysis_df['nws_max_temp'].std()
    }
    
    # Price analysis
    price_stats = {
        'min': analysis_df['kalshi_price'].min(),
        'max': analysis_df['kalshi_price'].max(),
        'mean': analysis_df['kalshi_price'].mean(),
        'std': analysis_df['kalshi_price'].std()
    }
    
    # Market performance
    won_markets = analysis_df[analysis_df['market_won']]
    lost_markets = analysis_df[~analysis_df['market_won']]
    
    print(f"\n📈 SUMMARY STATISTICS:")
    print(f"  Temperature Range: {temp_stats['min']:.1f}°F to {temp_stats['max']:.1f}°F")
    print(f"  Average Temperature: {temp_stats['mean']:.1f}°F ± {temp_stats['std']:.1f}°F")
    print(f"  Price Range: ${price_stats['min']/100:.2f} to ${price_stats['max']/100:.2f}")
    print(f"  Average Price: ${price_stats['mean']/100:.2f} ± ${price_stats['std']/100:.2f}")
    
    if len(won_markets) > 0 and len(lost_markets) > 0:
        print(f"\n💰 WINNING vs LOSING MARKETS:")
        print(f"  Winning markets avg price: ${won_markets['kalshi_price'].mean()/100:.2f}")
        print(f"  Losing markets avg price: ${lost_markets['kalshi_price'].mean()/100:.2f}")
        print(f"  Winning markets avg temp: {won_markets['nws_max_temp'].mean():.1f}°F")
        print(f"  Losing markets avg temp: {lost_markets['nws_max_temp'].mean():.1f}°F")
    
    print(f"\n✅ Analysis summary complete")

def main():
    """Main analysis function"""
    
    print("🚀 Starting Kalshi vs NWS Temperature Analysis")
    print("="*60)
    
    # Load Kalshi market data
    kalshi_df = load_kalshi_market_data()
    if kalshi_df.empty:
        print("❌ Cannot proceed without Kalshi data")
        return
    
    # Determine date range from Kalshi data
    event_dates = []
    for event_ticker in kalshi_df['event_ticker'].unique():
        event_date = extract_date_from_event_ticker(event_ticker)
        if event_date:
            event_dates.append(event_date)
    
    if not event_dates:
        print("❌ Could not extract dates from Kalshi event tickers")
        return
    
    start_date = min(event_dates)
    end_date = max(event_dates)
    
    print(f"📅 Analysis date range: {start_date} to {end_date}")
    
    # Get NWS settlement data
    nws_df = get_nws_settlement_data(start_date, end_date)
    
    # Perform analysis
    analysis_df = analyze_kalshi_vs_nws(kalshi_df, nws_df)
    
    # Save detailed results
    if not analysis_df.empty:
        filename = 'kalshi_vs_nws_detailed_analysis.csv'
        analysis_df.to_csv(filename, index=False)
        print(f"💾 Detailed analysis saved to {filename}")
    
    # Generate report
    create_analysis_report(analysis_df)
    
    # Create analysis summary
    create_simple_analysis_summary(analysis_df)
    
    print("\n🎉 Analysis complete!")

if __name__ == "__main__":
    main()