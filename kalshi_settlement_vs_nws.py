#!/usr/bin/env python3
"""
Kalshi Settlement Temperature vs NWS Daily Climate Report
Compare ACTUAL settlement temperatures (not markets/bets) - just two numbers per day
"""

import pandas as pd
import matplotlib.pyplot as plt
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

# Import our NWS source for official climate reports
from modules.kalshi_nws_source import KalshiNWSSource

def extract_settlement_temperature_from_kalshi_results(df: pd.DataFrame) -> pd.DataFrame:
    """Extract the actual settlement temperature from Kalshi market results"""
    
    print("🔍 Extracting actual settlement temperatures from Kalshi results...")
    
    # Group by date and find which market won (result='yes')
    settlement_temps = []
    
    for event_ticker in df['event_ticker'].unique():
        # Extract date from ticker
        date_match = re.match(r'KXHIGHNY-(\d{2})([A-Z]{3})(\d{2})', event_ticker)
        if not date_match:
            continue
            
        year_suffix, month_abbr, day = date_match.groups()
        year = 2000 + int(year_suffix)
        
        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        month = month_map.get(month_abbr)
        if not month:
            continue
            
        event_date = date(year, month, int(day))
        
        # Get all markets for this date that are finalized
        event_markets = df[
            (df['event_ticker'] == event_ticker) & 
            (df['status'] == 'finalized') & 
            (df['result'] == 'yes')
        ]
        
        if len(event_markets) == 0:
            print(f"  ❌ {event_date}: No winning market found")
            continue
        elif len(event_markets) > 1:
            print(f"  ⚠️ {event_date}: Multiple winning markets found - taking first")
        
        winning_market = event_markets.iloc[0]
        
        # Parse the temperature from the winning market subtitle
        settlement_temp = parse_settlement_temp_from_subtitle(winning_market['subtitle'])
        
        if settlement_temp:
            settlement_temps.append({
                'date': event_date,
                'kalshi_settlement_temp': settlement_temp,
                'winning_market': winning_market['subtitle']
            })
            print(f"  ✅ {event_date}: {settlement_temp}°F (from '{winning_market['subtitle']}')")
        else:
            print(f"  ❌ {event_date}: Could not parse temperature from '{winning_market['subtitle']}'")
    
    settlement_df = pd.DataFrame(settlement_temps)
    print(f"✅ Extracted {len(settlement_df)} Kalshi settlement temperatures")
    
    return settlement_df

def parse_settlement_temp_from_subtitle(subtitle: str) -> Optional[float]:
    """Parse the actual settlement temperature from the winning market subtitle"""
    
    # Range markets: "94° to 95°" -> use midpoint
    range_match = re.match(r'(\d+)° to (\d+)°', subtitle)
    if range_match:
        low, high = map(int, range_match.groups())
        return (low + high) / 2
    
    # Above markets: "94° or above" -> can't determine exact temp, skip
    above_match = re.match(r'(\d+)° or above', subtitle)
    if above_match:
        return None  # Can't determine exact temperature
    
    # Below markets: "85° or below" -> can't determine exact temp, skip  
    below_match = re.match(r'(\d+)° or below', subtitle)
    if below_match:
        return None  # Can't determine exact temperature
    
    return None

def get_nws_daily_climate_temps(start_date: date, end_date: date) -> pd.DataFrame:
    """Get official NWS daily climate report maximum temperatures"""
    
    print(f"🌡️ Getting NWS daily climate report max temps from {start_date} to {end_date}...")
    
    nws_source = KalshiNWSSource("KNYC")
    results = []
    
    current_date = start_date
    while current_date <= end_date:
        try:
            result = nws_source.get_daily_max_temperature(current_date)
            
            if result.get('max_temp') is not None:
                results.append({
                    'date': current_date,
                    'nws_max_temp': result['max_temp']
                })
                print(f"  ✅ {current_date}: {result['max_temp']}°F")
            else:
                print(f"  ❌ {current_date}: No NWS data - {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"  💥 {current_date}: Error - {e}")
        
        current_date += timedelta(days=1)
    
    nws_df = pd.DataFrame(results)
    print(f"✅ Retrieved {len(nws_df)} NWS daily climate temperatures")
    
    return nws_df

def create_simple_comparison(kalshi_df: pd.DataFrame, nws_df: pd.DataFrame) -> pd.DataFrame:
    """Create simple two-number comparison"""
    
    print("📊 Creating Kalshi Settlement vs NWS Daily Climate comparison...")
    
    # Merge the datasets
    comparison_df = kalshi_df.merge(nws_df, on='date', how='inner')
    
    if len(comparison_df) == 0:
        print("❌ No overlapping dates found between Kalshi and NWS data")
        return pd.DataFrame()
    
    # Calculate differences
    comparison_df['temp_difference'] = comparison_df['kalshi_settlement_temp'] - comparison_df['nws_max_temp']
    comparison_df['abs_difference'] = abs(comparison_df['temp_difference'])
    
    print(f"✅ Created comparison for {len(comparison_df)} days")
    
    return comparison_df

def create_comparison_report(comparison_df: pd.DataFrame) -> None:
    """Generate comparison report"""
    
    print("\n" + "="*80)
    print("📊 KALSHI SETTLEMENT vs NWS DAILY CLIMATE REPORT")
    print("="*80)
    
    if len(comparison_df) == 0:
        print("❌ No data available for comparison")
        return
    
    total_days = len(comparison_df)
    
    print(f"\n📈 OVERVIEW:")
    print(f"  Total days compared: {total_days}")
    print(f"  Date range: {comparison_df['date'].min()} to {comparison_df['date'].max()}")
    
    # Temperature statistics
    print(f"\n🌡️ TEMPERATURE STATISTICS:")
    print(f"  Kalshi settlement range: {comparison_df['kalshi_settlement_temp'].min():.1f}°F to {comparison_df['kalshi_settlement_temp'].max():.1f}°F")
    print(f"  NWS daily climate range: {comparison_df['nws_max_temp'].min():.1f}°F to {comparison_df['nws_max_temp'].max():.1f}°F")
    print(f"  Average Kalshi settlement: {comparison_df['kalshi_settlement_temp'].mean():.1f}°F")
    print(f"  Average NWS daily climate: {comparison_df['nws_max_temp'].mean():.1f}°F")
    
    # Difference analysis
    print(f"\n🔍 DIFFERENCE ANALYSIS:")
    print(f"  Mean difference (Kalshi - NWS): {comparison_df['temp_difference'].mean():.1f}°F")
    print(f"  Mean absolute difference: {comparison_df['abs_difference'].mean():.1f}°F")
    print(f"  Standard deviation of differences: {comparison_df['temp_difference'].std():.1f}°F")
    print(f"  Maximum absolute difference: {comparison_df['abs_difference'].max():.1f}°F")
    
    # Agreement analysis
    exact_matches = (comparison_df['abs_difference'] == 0).sum()
    within_1_degree = (comparison_df['abs_difference'] <= 1).sum()
    within_2_degrees = (comparison_df['abs_difference'] <= 2).sum()
    
    print(f"\n🎯 AGREEMENT ANALYSIS:")
    print(f"  Exact matches: {exact_matches}/{total_days} ({exact_matches/total_days:.1%})")
    print(f"  Within 1°F: {within_1_degree}/{total_days} ({within_1_degree/total_days:.1%})")
    print(f"  Within 2°F: {within_2_degrees}/{total_days} ({within_2_degrees/total_days:.1%})")
    
    # Daily breakdown
    print(f"\n📅 DAILY COMPARISON:")
    for _, row in comparison_df.iterrows():
        diff = row['temp_difference']
        abs_diff = row['abs_difference']
        
        if abs_diff == 0:
            match_emoji = "🎯"  # Perfect match
        elif abs_diff <= 1:
            match_emoji = "✅"  # Close match
        elif abs_diff <= 2:
            match_emoji = "⚠️"   # Moderate difference
        else:
            match_emoji = "❌"  # Large difference
        
        sign = "+" if diff > 0 else ""
        print(f"  {row['date']} {match_emoji}: Kalshi {row['kalshi_settlement_temp']:.1f}°F vs NWS {row['nws_max_temp']:.1f}°F ({sign}{diff:.1f}°F)")
    
    print(f"\n" + "="*80)

def create_temperature_comparison_chart(comparison_df: pd.DataFrame) -> None:
    """Create visual comparison of the two temperature sources"""
    
    print("📊 Creating temperature comparison visualization...")
    
    if len(comparison_df) == 0:
        print("❌ No data for visualization")
        return
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12))
    
    dates = comparison_df['date']
    kalshi_temps = comparison_df['kalshi_settlement_temp']
    nws_temps = comparison_df['nws_max_temp']
    differences = comparison_df['temp_difference']
    
    # 1. Temperature comparison line chart
    ax1.plot(dates, kalshi_temps, marker='o', linewidth=2, markersize=6, 
            color='blue', label='Kalshi Settlement Temperature', alpha=0.8)
    ax1.plot(dates, nws_temps, marker='s', linewidth=2, markersize=6, 
            color='red', label='NWS Daily Climate Report', alpha=0.8)
    
    ax1.set_ylabel('Temperature (°F)', fontsize=12, fontweight='bold')
    ax1.set_title('Kalshi Settlement vs NWS Daily Climate Report\nMaximum Temperatures', 
                 fontsize=14, fontweight='bold')
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)
    
    # 2. Scatter plot: Kalshi vs NWS
    ax2.scatter(nws_temps, kalshi_temps, alpha=0.7, s=80, color='purple')
    
    # Add perfect correlation line
    min_temp = min(min(kalshi_temps), min(nws_temps))
    max_temp = max(max(kalshi_temps), max(nws_temps))
    ax2.plot([min_temp, max_temp], [min_temp, max_temp], 'k--', alpha=0.5, label='Perfect Agreement')
    
    ax2.set_xlabel('NWS Daily Climate Report (°F)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Kalshi Settlement (°F)', fontsize=12, fontweight='bold')
    ax2.set_title('Temperature Correlation Analysis', fontsize=12, fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. Difference analysis
    colors = ['green' if abs(d) <= 1 else 'orange' if abs(d) <= 2 else 'red' for d in differences]
    bars = ax3.bar(range(len(dates)), differences, color=colors, alpha=0.7)
    
    ax3.axhline(y=0, color='black', linestyle='-', alpha=0.5)
    ax3.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Temperature Difference (°F)\n(Kalshi - NWS)', fontsize=12, fontweight='bold')
    ax3.set_title('Daily Temperature Differences', fontsize=12, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    
    # Set x-axis labels
    ax3.set_xticks(range(len(dates)))
    ax3.set_xticklabels([d.strftime('%m/%d') for d in dates], rotation=45)
    
    # Add statistics as text
    mean_diff = differences.mean()
    mean_abs_diff = abs(differences).mean()
    
    stats_text = f"""Statistics:
Mean Difference: {mean_diff:.1f}°F
Mean Abs Difference: {mean_abs_diff:.1f}°F
Within 1°F: {(abs(differences) <= 1).sum()}/{len(differences)} days"""
    
    ax3.text(0.02, 0.98, stats_text, transform=ax3.transAxes, fontsize=10,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    filename = 'kalshi_settlement_vs_nws_comparison.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Saved: {filename}")
    plt.show()

def main():
    """Main comparison function"""
    
    print("🚀 Kalshi Settlement Temperature vs NWS Daily Climate Report")
    print("="*70)
    
    # Load Kalshi market results
    print("📊 Loading Kalshi market data...")
    try:
        kalshi_df = pd.read_csv('kxhighny_markets_history.csv')
        print(f"✅ Loaded {len(kalshi_df)} Kalshi market records")
    except FileNotFoundError:
        print("❌ Kalshi market data not found. Please run the market search first.")
        return
    
    # Extract settlement temperatures from Kalshi results
    settlement_df = extract_settlement_temperature_from_kalshi_results(kalshi_df)
    
    if settlement_df.empty:
        print("❌ No settlement temperatures could be extracted from Kalshi data")
        return
    
    # Determine date range
    start_date = settlement_df['date'].min()
    end_date = settlement_df['date'].max()
    
    print(f"📅 Analysis period: {start_date} to {end_date}")
    
    # Get NWS daily climate data
    nws_df = get_nws_daily_climate_temps(start_date, end_date)
    
    if nws_df.empty:
        print("❌ No NWS daily climate data retrieved")
        return
    
    # Create comparison
    comparison_df = create_simple_comparison(settlement_df, nws_df)
    
    if comparison_df.empty:
        return
    
    # Save results
    filename = 'kalshi_settlement_vs_nws_daily_climate.csv'
    comparison_df.to_csv(filename, index=False)
    print(f"💾 Results saved to {filename}")
    
    # Generate report
    create_comparison_report(comparison_df)
    
    # Create visualization
    create_temperature_comparison_chart(comparison_df)
    
    print("\n🎉 Comparison complete!")

if __name__ == "__main__":
    main()