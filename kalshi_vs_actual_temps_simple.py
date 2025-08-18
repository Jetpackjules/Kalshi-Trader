#!/usr/bin/env python3
"""
Kalshi Settlement vs Actual Weather Data
Simple two-number comparison: Kalshi settlement temps vs real weather measurements
"""

import pandas as pd
import matplotlib.pyplot as plt
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

# Import our reliable weather APIs
from modules.nws_api import NWSAPI
from modules.synoptic_api import SynopticAPI
from modules.ncei_asos import NCEIASOS

def extract_kalshi_settlement_temps() -> pd.DataFrame:
    """Extract Kalshi settlement temperatures from market results"""
    
    print("🔍 Extracting Kalshi settlement temperatures...")
    
    try:
        df = pd.read_csv('kxhighny_markets_history.csv')
    except FileNotFoundError:
        print("❌ Kalshi market data not found")
        return pd.DataFrame()
    
    settlement_temps = []
    
    for event_ticker in df['event_ticker'].unique():
        # Extract date from ticker (KXHIGHNY-25JUL30)
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
        
        # Find the winning market for this date
        winning_markets = df[
            (df['event_ticker'] == event_ticker) & 
            (df['status'] == 'finalized') & 
            (df['result'] == 'yes')
        ]
        
        if len(winning_markets) == 0:
            continue
        
        winning_market = winning_markets.iloc[0]
        
        # Parse temperature from winning market subtitle (only range markets)
        settlement_temp = parse_temp_from_range_subtitle(winning_market['subtitle'])
        
        if settlement_temp:
            settlement_temps.append({
                'date': event_date,
                'kalshi_settlement_temp': settlement_temp,
                'winning_market': winning_market['subtitle']
            })
            print(f"  ✅ {event_date}: {settlement_temp}°F (from '{winning_market['subtitle']}')")
    
    settlement_df = pd.DataFrame(settlement_temps)
    print(f"✅ Extracted {len(settlement_df)} Kalshi settlement temperatures")
    
    return settlement_df

def parse_temp_from_range_subtitle(subtitle: str) -> Optional[float]:
    """Parse temperature from range markets only (e.g., '94° to 95°' -> 94.5)"""
    
    # Only process range markets: "X° to Y°"
    range_match = re.match(r'(\d+)° to (\d+)°', subtitle)
    if range_match:
        low, high = map(int, range_match.groups())
        return (low + high) / 2  # Use midpoint of range
    
    return None  # Skip "or above" and "or below" markets

def get_actual_weather_temps(dates: List[date]) -> pd.DataFrame:
    """Get actual weather temperatures for the given dates"""
    
    print(f"🌡️ Getting actual weather data for {len(dates)} dates...")
    
    # Use our most reliable weather APIs
    nws = NWSAPI("KNYC")
    synoptic = SynopticAPI("KNYC") 
    asos = NCEIASOS("KNYC")
    
    results = []
    
    for target_date in sorted(dates):
        row = {'date': target_date}
        temps = []
        
        # Try NWS API
        try:
            nws_result = nws.get_daily_max_temperature(target_date)
            if nws_result.get('max_temp'):
                row['nws_temp'] = nws_result['max_temp']
                temps.append(nws_result['max_temp'])
        except:
            pass
        
        # Try Synoptic API
        try:
            syn_result = synoptic.get_daily_max_temperature(target_date)
            if syn_result.get('max_temp'):
                row['synoptic_temp'] = syn_result['max_temp']
                temps.append(syn_result['max_temp'])
        except:
            pass
        
        # Try ASOS
        try:
            asos_result = asos.get_daily_max_temperature(target_date)
            if asos_result.get('max_temp'):
                row['asos_temp'] = asos_result['max_temp']
                temps.append(asos_result['max_temp'])
        except:
            pass
        
        # Calculate best temperature estimate
        if temps:
            row['actual_temp'] = round(sum(temps) / len(temps), 1)
            row['temp_sources'] = len(temps)
            print(f"  ✅ {target_date}: {row['actual_temp']}°F (from {row['temp_sources']} sources)")
        else:
            print(f"  ❌ {target_date}: No weather data")
        
        results.append(row)
    
    weather_df = pd.DataFrame(results)
    print(f"✅ Retrieved weather data for {len(weather_df)} dates")
    
    return weather_df

def create_comparison_analysis(kalshi_df: pd.DataFrame, weather_df: pd.DataFrame) -> pd.DataFrame:
    """Create the simple two-number comparison"""
    
    print("📊 Creating Kalshi vs Actual Temperature Comparison...")
    
    # Merge datasets
    comparison_df = kalshi_df.merge(weather_df, on='date', how='inner')
    
    # Only keep rows where we have both Kalshi settlement and actual weather data
    comparison_df = comparison_df[comparison_df['actual_temp'].notna()].copy()
    
    if len(comparison_df) == 0:
        print("❌ No overlapping data found")
        return pd.DataFrame()
    
    # Calculate differences
    comparison_df['temp_difference'] = comparison_df['kalshi_settlement_temp'] - comparison_df['actual_temp']
    comparison_df['abs_difference'] = abs(comparison_df['temp_difference'])
    
    print(f"✅ Created comparison for {len(comparison_df)} days")
    
    return comparison_df

def create_comparison_report(comparison_df: pd.DataFrame) -> None:
    """Generate detailed comparison report"""
    
    print("\n" + "="*80)
    print("📊 KALSHI SETTLEMENT vs ACTUAL WEATHER TEMPERATURES")
    print("   (Two Numbers Per Day Comparison)")
    print("="*80)
    
    if len(comparison_df) == 0:
        print("❌ No data available for comparison")
        return
    
    total_days = len(comparison_df)
    
    print(f"\n📈 OVERVIEW:")
    print(f"  Total days compared: {total_days}")
    print(f"  Date range: {comparison_df['date'].min()} to {comparison_df['date'].max()}")
    
    # Temperature statistics
    kalshi_temps = comparison_df['kalshi_settlement_temp']
    actual_temps = comparison_df['actual_temp']
    differences = comparison_df['temp_difference'] 
    abs_differences = comparison_df['abs_difference']
    
    print(f"\n🌡️ TEMPERATURE STATISTICS:")
    print(f"  Kalshi settlement range: {kalshi_temps.min():.1f}°F to {kalshi_temps.max():.1f}°F")
    print(f"  Actual weather range: {actual_temps.min():.1f}°F to {actual_temps.max():.1f}°F")
    print(f"  Average Kalshi settlement: {kalshi_temps.mean():.1f}°F")
    print(f"  Average actual weather: {actual_temps.mean():.1f}°F")
    
    # Difference analysis
    print(f"\n🔍 DIFFERENCE ANALYSIS:")
    print(f"  Mean difference (Kalshi - Actual): {differences.mean():.1f}°F")
    print(f"  Mean absolute difference: {abs_differences.mean():.1f}°F")
    print(f"  Standard deviation: {differences.std():.1f}°F")
    print(f"  Largest absolute difference: {abs_differences.max():.1f}°F")
    
    # Agreement analysis
    exact_matches = (abs_differences == 0).sum()
    within_1_degree = (abs_differences <= 1).sum()
    within_2_degrees = (abs_differences <= 2).sum()
    within_3_degrees = (abs_differences <= 3).sum()
    
    print(f"\n🎯 AGREEMENT ANALYSIS:")
    print(f"  Exact matches: {exact_matches}/{total_days} ({exact_matches/total_days:.1%})")
    print(f"  Within 1°F: {within_1_degree}/{total_days} ({within_1_degree/total_days:.1%})")
    print(f"  Within 2°F: {within_2_degrees}/{total_days} ({within_2_degrees/total_days:.1%})")
    print(f"  Within 3°F: {within_3_degrees}/{total_days} ({within_3_degrees/total_days:.1%})")
    
    # Bias analysis
    kalshi_higher = (differences > 0).sum()
    actual_higher = (differences < 0).sum()
    
    print(f"\n⚖️ BIAS ANALYSIS:")
    print(f"  Kalshi higher than actual: {kalshi_higher}/{total_days} ({kalshi_higher/total_days:.1%})")
    print(f"  Actual higher than Kalshi: {actual_higher}/{total_days} ({actual_higher/total_days:.1%})")
    
    # Daily breakdown (most recent first)
    print(f"\n📅 DAILY COMPARISON (Recent First):")
    recent_df = comparison_df.sort_values('date', ascending=False).head(20)
    
    for _, row in recent_df.iterrows():
        diff = row['temp_difference']
        abs_diff = row['abs_difference']
        
        if abs_diff == 0:
            match_emoji = "🎯"  # Perfect match
        elif abs_diff <= 1:
            match_emoji = "✅"  # Very close
        elif abs_diff <= 2:
            match_emoji = "⚠️"   # Close
        elif abs_diff <= 3:
            match_emoji = "🔸"  # Moderate
        else:
            match_emoji = "❌"  # Large difference
        
        sign = "+" if diff > 0 else ""
        sources_info = f"({row['temp_sources']} sources)" if 'temp_sources' in row else ""
        
        print(f"  {row['date']} {match_emoji}: Kalshi {row['kalshi_settlement_temp']:.1f}°F vs Actual {row['actual_temp']:.1f}°F ({sign}{diff:.1f}°F) {sources_info}")
    
    print(f"\n" + "="*80)

def create_temperature_comparison_visual(comparison_df: pd.DataFrame) -> None:
    """Create visual comparison of Kalshi vs Actual temperatures"""
    
    print("📊 Creating temperature comparison visualization...")
    
    if len(comparison_df) == 0:
        print("❌ No data for visualization")
        return
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    dates = comparison_df['date']
    kalshi_temps = comparison_df['kalshi_settlement_temp']
    actual_temps = comparison_df['actual_temp']
    differences = comparison_df['temp_difference']
    
    # 1. Temperature comparison line chart
    ax1.plot(dates, kalshi_temps, marker='o', linewidth=2, markersize=6, 
            color='blue', label='Kalshi Settlement', alpha=0.8)
    ax1.plot(dates, actual_temps, marker='s', linewidth=2, markersize=6, 
            color='red', label='Actual Weather Data', alpha=0.8)
    
    ax1.set_ylabel('Temperature (°F)', fontsize=12, fontweight='bold')
    ax1.set_title('Kalshi Settlement vs Actual Weather Temperatures', 
                 fontsize=14, fontweight='bold')
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis='x', rotation=45)
    
    # 2. Scatter plot: Kalshi vs Actual
    ax2.scatter(actual_temps, kalshi_temps, alpha=0.7, s=80, color='purple')
    
    # Add perfect correlation line
    min_temp = min(min(kalshi_temps), min(actual_temps))
    max_temp = max(max(kalshi_temps), max(actual_temps))
    ax2.plot([min_temp, max_temp], [min_temp, max_temp], 'k--', alpha=0.5, label='Perfect Agreement')
    
    ax2.set_xlabel('Actual Weather Temperature (°F)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Kalshi Settlement Temperature (°F)', fontsize=12, fontweight='bold')
    ax2.set_title('Temperature Correlation Analysis', fontsize=12, fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. Difference analysis
    colors = ['green' if abs(d) <= 1 else 'orange' if abs(d) <= 2 else 'red' for d in differences]
    bars = ax3.bar(range(len(dates)), differences, color=colors, alpha=0.7)
    
    ax3.axhline(y=0, color='black', linestyle='-', alpha=0.5)
    ax3.set_xlabel('Date Index', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Temperature Difference (°F)\n(Kalshi - Actual)', fontsize=12, fontweight='bold')
    ax3.set_title('Daily Temperature Differences', fontsize=12, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    
    # 4. Difference histogram
    ax4.hist(differences, bins=15, alpha=0.7, color='steelblue', edgecolor='black')
    ax4.axvline(differences.mean(), color='red', linestyle='--', linewidth=2, 
               label=f'Mean: {differences.mean():.1f}°F')
    ax4.axvline(0, color='black', linestyle='-', alpha=0.5, label='Perfect Agreement')
    
    ax4.set_xlabel('Temperature Difference (°F)', fontsize=12, fontweight='bold')
    ax4.set_ylabel('Frequency', fontsize=12, fontweight='bold')
    ax4.set_title('Distribution of Temperature Differences', fontsize=12, fontweight='bold')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    # Add summary statistics
    mean_abs_diff = abs(differences).mean()
    within_1_deg = (abs(differences) <= 1).sum() / len(differences)
    
    stats_text = f"""Summary Statistics:
Days Compared: {len(differences)}
Mean Abs Difference: {mean_abs_diff:.1f}°F
Within 1°F: {within_1_deg:.1%}
Correlation: {actual_temps.corr(kalshi_temps):.3f}"""
    
    ax4.text(0.02, 0.98, stats_text, transform=ax4.transAxes, fontsize=10,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    filename = 'kalshi_settlement_vs_actual_weather.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Saved: {filename}")
    plt.show()

def main():
    """Main comparison function"""
    
    print("🚀 Kalshi Settlement vs Actual Weather Temperature Comparison")
    print("="*70)
    
    # Extract Kalshi settlement temperatures
    kalshi_df = extract_kalshi_settlement_temps()
    
    if kalshi_df.empty:
        print("❌ No Kalshi settlement temperatures found")
        return
    
    # Get actual weather data for those dates
    dates = kalshi_df['date'].tolist()
    weather_df = get_actual_weather_temps(dates)
    
    # Create comparison
    comparison_df = create_comparison_analysis(kalshi_df, weather_df)
    
    if comparison_df.empty:
        print("❌ No overlapping data for comparison")
        return
    
    # Save results
    filename = 'kalshi_settlement_vs_actual_weather.csv'
    comparison_df.to_csv(filename, index=False)
    print(f"💾 Results saved to {filename}")
    
    # Generate report
    create_comparison_report(comparison_df)
    
    # Create visualization
    create_temperature_comparison_visual(comparison_df)
    
    print("\n🎉 Two-number comparison complete!")

if __name__ == "__main__":
    main()