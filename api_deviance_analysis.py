#!/usr/bin/env python3
"""
Weather API Deviance Analysis vs Kalshi Winning Intervals
Find which API has lowest average deviance from actual winning temperature ranges
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

# Import our weather APIs
from modules.nws_api import NWSAPI
from modules.synoptic_api import SynopticAPI
from modules.ncei_asos import NCEIASOS

def load_kalshi_winning_intervals() -> pd.DataFrame:
    """Load Kalshi market data and extract winning intervals"""
    
    print("🔍 Loading Kalshi winning intervals...")
    
    try:
        df = pd.read_csv('kxhighny_markets_history.csv')
    except FileNotFoundError:
        print("❌ Kalshi market data not found")
        return pd.DataFrame()
    
    winning_intervals = []
    
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
        
        # Find winning market (result='yes')
        winning_markets = df[
            (df['event_ticker'] == event_ticker) & 
            (df['status'] == 'finalized') & 
            (df['result'] == 'yes')
        ]
        
        if len(winning_markets) == 0:
            continue
        
        winning_market = winning_markets.iloc[0]
        interval = parse_winning_interval(winning_market['subtitle'])
        
        if interval:
            winning_intervals.append({
                'date': event_date,
                'winning_subtitle': winning_market['subtitle'],
                'interval_type': interval['type'],
                'interval_low': interval.get('low'),
                'interval_high': interval.get('high'),
                'interval_threshold': interval.get('threshold')
            })
            print(f"  ✅ {event_date}: {winning_market['subtitle']} → {interval}")
    
    intervals_df = pd.DataFrame(winning_intervals)
    print(f"✅ Extracted {len(intervals_df)} winning intervals")
    
    return intervals_df

def parse_winning_interval(subtitle: str) -> Optional[Dict]:
    """Parse the winning interval from subtitle"""
    
    # Range: "94° to 95°" 
    range_match = re.match(r'(\d+)° to (\d+)°', subtitle)
    if range_match:
        low, high = map(int, range_match.groups())
        return {'type': 'range', 'low': low, 'high': high}
    
    # Above: "94° or above"
    above_match = re.match(r'(\d+)° or above', subtitle)
    if above_match:
        threshold = int(above_match.group(1))
        return {'type': 'above', 'threshold': threshold}
    
    # Below: "85° or below"
    below_match = re.match(r'(\d+)° or below', subtitle)
    if below_match:
        threshold = int(below_match.group(1))
        return {'type': 'below', 'threshold': threshold}
    
    return None

def calculate_deviance_from_interval(predicted_temp: float, interval_info: Dict) -> float:
    """Calculate deviance from winning interval"""
    
    interval_type = interval_info['interval_type']
    
    if interval_type == 'range':
        low = interval_info['interval_low']
        high = interval_info['interval_high']
        
        if low <= predicted_temp <= high:
            return 0.0  # Within interval = 0 deviance
        elif predicted_temp < low:
            return low - predicted_temp  # Below interval
        else:
            return predicted_temp - high  # Above interval
    
    elif interval_type == 'above':
        threshold = interval_info['interval_threshold']
        if predicted_temp >= threshold:
            return 0.0  # Correctly above
        else:
            return threshold - predicted_temp  # Below threshold
    
    elif interval_type == 'below':
        threshold = interval_info['interval_threshold']
        if predicted_temp <= threshold:
            return 0.0  # Correctly below
        else:
            return predicted_temp - threshold  # Above threshold
    
    return float('inf')  # Unknown interval type

def get_weather_data_for_intervals(intervals_df: pd.DataFrame) -> pd.DataFrame:
    """Get weather data for all the interval dates"""
    
    print(f"🌡️ Getting weather data for {len(intervals_df)} dates...")
    
    # Initialize APIs
    nws = NWSAPI("KNYC")
    synoptic = SynopticAPI("KNYC")
    asos = NCEIASOS("KNYC")
    
    results = []
    
    for _, interval_row in intervals_df.iterrows():
        target_date = interval_row['date']
        row = {
            'date': target_date,
            'winning_subtitle': interval_row['winning_subtitle'],
            'interval_type': interval_row['interval_type'],
            'interval_low': interval_row['interval_low'],
            'interval_high': interval_row['interval_high'],
            'interval_threshold': interval_row['interval_threshold']
        }
        
        # Try each API
        apis_tried = []
        
        # NWS API
        try:
            nws_result = nws.get_daily_max_temperature(target_date)
            if nws_result.get('max_temp'):
                row['nws_temp'] = nws_result['max_temp']
                row['nws_count'] = nws_result.get('count', 0)
                apis_tried.append('NWS')
        except Exception as e:
            print(f"    NWS error for {target_date}: {e}")
        
        # Synoptic API
        try:
            syn_result = synoptic.get_daily_max_temperature(target_date)
            if syn_result.get('max_temp'):
                row['synoptic_temp'] = syn_result['max_temp']
                row['synoptic_count'] = syn_result.get('count', 0)
                apis_tried.append('Synoptic')
        except Exception as e:
            print(f"    Synoptic error for {target_date}: {e}")
        
        # ASOS API
        try:
            asos_result = asos.get_daily_max_temperature(target_date)
            if asos_result.get('max_temp'):
                row['asos_temp'] = asos_result['max_temp']
                row['asos_count'] = asos_result.get('count', 0)
                apis_tried.append('ASOS')
        except Exception as e:
            print(f"    ASOS error for {target_date}: {e}")
        
        if apis_tried:
            print(f"  ✅ {target_date}: {', '.join(apis_tried)} APIs successful")
        else:
            print(f"  ❌ {target_date}: No APIs successful")
        
        results.append(row)
    
    weather_df = pd.DataFrame(results)
    print(f"✅ Retrieved weather data for {len(weather_df)} dates")
    
    return weather_df

def calculate_api_deviances(weather_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate deviances for each API"""
    
    print("📊 Calculating API deviances from winning intervals...")
    
    # Calculate deviances for each API
    for api in ['nws', 'synoptic', 'asos']:
        temp_col = f'{api}_temp'
        deviance_col = f'{api}_deviance'
        match_col = f'{api}_exact_match'
        
        if temp_col in weather_df.columns:
            deviances = []
            exact_matches = []
            
            for _, row in weather_df.iterrows():
                if pd.notna(row[temp_col]):
                    interval_info = {
                        'interval_type': row['interval_type'],
                        'interval_low': row['interval_low'],
                        'interval_high': row['interval_high'],
                        'interval_threshold': row['interval_threshold']
                    }
                    
                    deviance = calculate_deviance_from_interval(row[temp_col], interval_info)
                    exact_match = (deviance == 0.0)
                    
                    deviances.append(deviance)
                    exact_matches.append(exact_match)
                else:
                    deviances.append(np.nan)
                    exact_matches.append(np.nan)
            
            weather_df[deviance_col] = deviances
            weather_df[match_col] = exact_matches
    
    print("✅ Calculated deviances for all APIs")
    
    return weather_df

def create_api_performance_summary(weather_df: pd.DataFrame) -> pd.DataFrame:
    """Create performance summary for each API"""
    
    print("📈 Creating API performance summary...")
    
    apis = ['nws', 'synoptic', 'asos']
    api_names = ['NWS API', 'Synoptic API', 'NCEI ASOS']
    
    summary_data = []
    
    for api, api_name in zip(apis, api_names):
        temp_col = f'{api}_temp'
        deviance_col = f'{api}_deviance'
        match_col = f'{api}_exact_match'
        count_col = f'{api}_count'
        
        if temp_col not in weather_df.columns:
            continue
        
        # Filter to rows where this API has data
        api_data = weather_df[weather_df[temp_col].notna()].copy()
        
        if len(api_data) == 0:
            continue
        
        # Calculate metrics
        total_days = len(api_data)
        avg_deviance = api_data[deviance_col].mean()
        median_deviance = api_data[deviance_col].median()
        max_deviance = api_data[deviance_col].max()
        std_deviance = api_data[deviance_col].std()
        
        exact_matches = api_data[match_col].sum()
        exact_match_pct = (exact_matches / total_days) * 100
        
        # Average observation count (data quality metric)
        avg_obs_count = api_data[count_col].mean() if count_col in api_data.columns else 0
        
        summary_data.append({
            'API': api_name,
            'api_code': api,
            'total_days': total_days,
            'avg_deviance': avg_deviance,
            'median_deviance': median_deviance,
            'max_deviance': max_deviance,
            'std_deviance': std_deviance,
            'exact_matches': exact_matches,
            'exact_match_pct': exact_match_pct,
            'avg_obs_count': avg_obs_count
        })
        
        print(f"  ✅ {api_name}: {total_days} days, {avg_deviance:.2f}°F avg deviance, {exact_match_pct:.1f}% exact matches")
    
    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values('avg_deviance')  # Best (lowest deviance) first
    
    print("✅ Performance summary created")
    
    return summary_df

def create_deviance_visualizations(weather_df: pd.DataFrame, summary_df: pd.DataFrame) -> None:
    """Create comprehensive deviance visualizations"""
    
    print("📊 Creating deviance analysis visualizations...")
    
    if summary_df.empty:
        print("❌ No data for visualization")
        return
    
    # Set up the plotting style
    plt.style.use('default')
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. Average Deviance Comparison (Main Chart)
    api_names = summary_df['API'].tolist()
    avg_deviances = summary_df['avg_deviance'].tolist()
    
    colors = ['green', 'blue', 'orange'][:len(api_names)]
    bars1 = ax1.bar(api_names, avg_deviances, color=colors, alpha=0.8, edgecolor='black', linewidth=1)
    
    ax1.set_ylabel('Average Deviance (°F)', fontsize=12, fontweight='bold')
    ax1.set_title('🏆 Weather API Performance:\nAverage Deviance from Kalshi Winning Intervals', 
                 fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    
    # Add value labels on bars
    for i, (bar, deviance) in enumerate(zip(bars1, avg_deviances)):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05, 
                f'{deviance:.2f}°F', ha='center', va='bottom', fontweight='bold', fontsize=11)
        
        # Add ranking
        rank = i + 1
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height()/2, 
                f'#{rank}', ha='center', va='center', fontweight='bold', 
                fontsize=14, color='white' if deviance > 0.3 else 'black')
    
    # 2. Exact Match Percentages
    exact_match_pcts = summary_df['exact_match_pct'].tolist()
    
    bars2 = ax2.bar(api_names, exact_match_pcts, color=colors, alpha=0.8, edgecolor='black', linewidth=1)
    
    ax2.set_ylabel('Exact Match Percentage (%)', fontsize=12, fontweight='bold')
    ax2.set_title('🎯 Exact Matches Within Winning Intervals', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(0, 100)
    
    # Add percentage labels
    for bar, pct in zip(bars2, exact_match_pcts):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                f'{pct:.1f}%', ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    # 3. Data Coverage (Days Available)
    total_days = summary_df['total_days'].tolist()
    
    bars3 = ax3.bar(api_names, total_days, color=colors, alpha=0.8, edgecolor='black', linewidth=1)
    
    ax3.set_ylabel('Days with Data Available', fontsize=12, fontweight='bold')
    ax3.set_title('📅 Data Coverage by API', fontsize=14, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    
    # Add count labels
    for bar, days in zip(bars3, total_days):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                f'{days}', ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    # 4. Deviance Distribution (Box Plot)
    deviance_data = []
    api_labels = []
    
    for _, row in summary_df.iterrows():
        api_code = row['api_code']
        deviance_col = f'{api_code}_deviance'
        
        if deviance_col in weather_df.columns:
            api_deviances = weather_df[deviance_col].dropna().tolist()
            deviance_data.extend(api_deviances)
            api_labels.extend([row['API']] * len(api_deviances))
    
    if deviance_data:
        # Create box plot data
        plot_data = pd.DataFrame({'API': api_labels, 'Deviance': deviance_data})
        
        box_plot = ax4.boxplot([plot_data[plot_data['API'] == api]['Deviance'].tolist() 
                               for api in api_names], 
                              labels=api_names, patch_artist=True)
        
        # Color the boxes
        for patch, color in zip(box_plot['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.8)
        
        ax4.set_ylabel('Deviance (°F)', fontsize=12, fontweight='bold')
        ax4.set_title('📊 Deviance Distribution by API', fontsize=14, fontweight='bold')
        ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save visualization
    filename = 'api_deviance_analysis.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Saved: {filename}")
    plt.show()

def generate_api_recommendation(summary_df: pd.DataFrame) -> None:
    """Generate API recommendation based on analysis"""
    
    print("\n" + "="*80)
    print("🏆 WEATHER API DEVIANCE ANALYSIS - FINAL RECOMMENDATION")
    print("="*80)
    
    if summary_df.empty:
        print("❌ No data available for recommendation")
        return
    
    best_api = summary_df.iloc[0]  # Already sorted by avg_deviance
    
    print(f"\n🥇 WINNER: {best_api['API']}")
    print(f"   Average Deviance: {best_api['avg_deviance']:.2f}°F")
    print(f"   Exact Match Rate: {best_api['exact_match_pct']:.1f}%")
    print(f"   Data Coverage: {best_api['total_days']} days")
    
    print(f"\n📊 COMPLETE RANKINGS:")
    for i, (_, row) in enumerate(summary_df.iterrows()):
        rank = i + 1
        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
        
        print(f"   {medal} {row['API']}:")
        print(f"      • Average Deviance: {row['avg_deviance']:.2f}°F")
        print(f"      • Exact Matches: {row['exact_matches']}/{row['total_days']} ({row['exact_match_pct']:.1f}%)")
        print(f"      • Max Deviance: {row['max_deviance']:.2f}°F")
        print(f"      • Avg Observations: {row['avg_obs_count']:.0f} per day")
        print()
    
    # Generate specific recommendation
    print(f"💡 TRADING RECOMMENDATION:")
    
    if best_api['avg_deviance'] < 1.0:
        accuracy_rating = "EXCELLENT"
    elif best_api['avg_deviance'] < 2.0:
        accuracy_rating = "VERY GOOD"
    elif best_api['avg_deviance'] < 3.0:
        accuracy_rating = "GOOD"
    else:
        accuracy_rating = "MODERATE"
    
    print(f"   📈 Use {best_api['API']} for temperature predictions")
    print(f"   🎯 Accuracy Rating: {accuracy_rating}")
    print(f"   📊 Expected Performance: ~{best_api['exact_match_pct']:.0f}% exact matches")
    
    if best_api['avg_deviance'] < 1.5:
        print(f"   ✅ This API shows strong reliability for Kalshi trading")
    else:
        print(f"   ⚠️ Consider combining multiple APIs for better accuracy")
    
    # Specific insights
    if len(summary_df) > 1:
        second_best = summary_df.iloc[1]
        diff = second_best['avg_deviance'] - best_api['avg_deviance']
        
        print(f"\n🔍 KEY INSIGHTS:")
        print(f"   • {best_api['API']} outperforms {second_best['API']} by {diff:.2f}°F on average")
        
        if best_api['exact_match_pct'] > 50:
            print(f"   • {best_api['API']} correctly predicts winning interval >50% of the time")
        
        if best_api['avg_obs_count'] > 50:
            print(f"   • High data quality with {best_api['avg_obs_count']:.0f} observations per day on average")
    
    print(f"\n" + "="*80)

def main():
    """Main analysis function"""
    
    print("🚀 Weather API Deviance Analysis vs Kalshi Winning Intervals")
    print("="*70)
    
    # Load Kalshi winning intervals
    intervals_df = load_kalshi_winning_intervals()
    
    if intervals_df.empty:
        print("❌ No winning intervals found")
        return
    
    # Get weather data for those dates
    weather_df = get_weather_data_for_intervals(intervals_df)
    
    # Calculate deviances
    weather_df = calculate_api_deviances(weather_df)
    
    # Create performance summary
    summary_df = create_api_performance_summary(weather_df)
    
    if summary_df.empty:
        print("❌ No API performance data available")
        return
    
    # Save detailed results
    weather_filename = 'api_deviance_detailed_results.csv'
    weather_df.to_csv(weather_filename, index=False)
    print(f"💾 Detailed results saved to {weather_filename}")
    
    summary_filename = 'api_performance_summary.csv'
    summary_df.to_csv(summary_filename, index=False)
    print(f"💾 Summary results saved to {summary_filename}")
    
    # Create visualizations
    create_deviance_visualizations(weather_df, summary_df)
    
    # Generate recommendation
    generate_api_recommendation(summary_df)
    
    print("\n🎉 API deviance analysis complete!")

if __name__ == "__main__":
    main()