#!/usr/bin/env python3
"""
Simple Kalshi vs Temperature Comparison
Using our reliable weather APIs and Kalshi historical market results
"""

import pandas as pd
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

# Import our reliable weather APIs
from modules.nws_api import NWSAPI
from modules.synoptic_api import SynopticAPI
from modules.ncei_asos import NCEIASOS

def load_kalshi_data() -> pd.DataFrame:
    """Load Kalshi market data"""
    
    print("📊 Loading Kalshi KXHIGHNY market data...")
    
    try:
        df = pd.read_csv('kxhighny_markets_history.csv')
        print(f"✅ Loaded {len(df)} Kalshi market records")
        return df
    except FileNotFoundError:
        print("❌ Kalshi data not found. Please run the Kalshi search first.")
        return pd.DataFrame()

def extract_date_from_ticker(ticker: str) -> Optional[date]:
    """Extract date from KXHIGHNY-25JUL30 format"""
    match = re.match(r'KXHIGHNY-(\d{2})([A-Z]{3})(\d{2})', ticker)
    if not match:
        return None
    
    year_suffix, month_abbr, day = match.groups()
    year = 2000 + int(year_suffix)
    
    month_map = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    month = month_map.get(month_abbr)
    if not month:
        return None
    
    return date(year, month, int(day))

def extract_temp_from_subtitle(subtitle: str) -> Dict:
    """Extract temperature info from market subtitle"""
    
    # Range: "94° to 95°"
    range_match = re.match(r'(\d+)° to (\d+)°', subtitle)
    if range_match:
        low, high = map(int, range_match.groups())
        return {'type': 'range', 'low': low, 'high': high, 'midpoint': (low + high) / 2}
    
    # Above: "94° or above"
    above_match = re.match(r'(\d+)° or above', subtitle)
    if above_match:
        threshold = int(above_match.group(1))
        return {'type': 'above', 'threshold': threshold, 'midpoint': threshold + 3}
    
    # Below: "85° or below"  
    below_match = re.match(r'(\d+)° or below', subtitle)
    if below_match:
        threshold = int(below_match.group(1))
        return {'type': 'below', 'threshold': threshold, 'midpoint': threshold - 3}
    
    return {'type': 'unknown', 'midpoint': None}

def get_weather_data_for_date_range(start_date: date, end_date: date) -> pd.DataFrame:
    """Get weather data from our reliable APIs"""
    
    print(f"🌡️ Getting weather data from {start_date} to {end_date}...")
    
    # Use our best weather APIs
    nws = NWSAPI("KNYC")
    synoptic = SynopticAPI("KNYC") 
    asos = NCEIASOS("KNYC")
    
    results = []
    current_date = start_date
    
    while current_date <= end_date:
        row = {'date': current_date}
        
        # Try NWS API first
        try:
            nws_result = nws.get_daily_max_temperature(current_date)
            if nws_result.get('max_temp'):
                row['nws_temp'] = nws_result['max_temp']
                row['nws_time'] = nws_result.get('max_time', '')
                row['nws_count'] = nws_result.get('count', 0)
        except:
            pass
        
        # Try Synoptic API
        try:
            syn_result = synoptic.get_daily_max_temperature(current_date)
            if syn_result.get('max_temp'):
                row['synoptic_temp'] = syn_result['max_temp']
                row['synoptic_time'] = syn_result.get('max_time', '')
                row['synoptic_count'] = syn_result.get('count', 0)
        except:
            pass
        
        # Try ASOS
        try:
            asos_result = asos.get_daily_max_temperature(current_date)
            if asos_result.get('max_temp'):
                row['asos_temp'] = asos_result['max_temp']
                row['asos_time'] = asos_result.get('max_time', '')
                row['asos_count'] = asos_result.get('count', 0)
        except:
            pass
        
        # Determine best temperature estimate
        temps = []
        if 'nws_temp' in row:
            temps.append(row['nws_temp'])
        if 'synoptic_temp' in row:
            temps.append(row['synoptic_temp'])
        if 'asos_temp' in row:
            temps.append(row['asos_temp'])
        
        if temps:
            row['best_temp'] = round(sum(temps) / len(temps), 1)
            row['temp_sources'] = len(temps)
            print(f"  ✅ {current_date}: {row['best_temp']}°F (from {row['temp_sources']} sources)")
        else:
            print(f"  ❌ {current_date}: No temperature data")
        
        results.append(row)
        current_date += timedelta(days=1)
    
    return pd.DataFrame(results)

def analyze_kalshi_accuracy(kalshi_df: pd.DataFrame, weather_df: pd.DataFrame) -> pd.DataFrame:
    """Analyze how accurate Kalshi markets were"""
    
    print("🔍 Analyzing Kalshi market accuracy...")
    
    # Process Kalshi data
    kalshi_processed = []
    
    for _, row in kalshi_df.iterrows():
        if row['status'] != 'finalized' or row['result'] not in ['yes', 'no']:
            continue
            
        event_date = extract_date_from_ticker(row['event_ticker'])
        if not event_date:
            continue
        
        temp_info = extract_temp_from_subtitle(row['subtitle'])
        
        kalshi_processed.append({
            'date': event_date,
            'event_ticker': row['event_ticker'],
            'subtitle': row['subtitle'],
            'temp_type': temp_info['type'],
            'temp_low': temp_info.get('low'),
            'temp_high': temp_info.get('high'),
            'temp_threshold': temp_info.get('threshold'),
            'temp_midpoint': temp_info.get('midpoint'),
            'kalshi_price': row['last_price'],
            'kalshi_result': row['result'],
            'market_won': row['result'] == 'yes'
        })
    
    kalshi_df_processed = pd.DataFrame(kalshi_processed)
    
    # Merge with weather data
    merged = kalshi_df_processed.merge(weather_df, on='date', how='inner')
    
    # Only keep rows where we have both Kalshi results and weather data
    analysis_df = merged[merged['best_temp'].notna()].copy()
    
    # Determine if the market prediction was correct
    def was_prediction_correct(row):
        actual_temp = row['best_temp']
        temp_type = row['temp_type']
        market_won = row['market_won']
        
        if temp_type == 'range':
            temp_in_range = row['temp_low'] <= actual_temp <= row['temp_high']
        elif temp_type == 'above':
            temp_in_range = actual_temp >= row['temp_threshold']
        elif temp_type == 'below':
            temp_in_range = actual_temp <= row['temp_threshold']
        else:
            return None
        
        return market_won == temp_in_range
    
    analysis_df['prediction_correct'] = analysis_df.apply(was_prediction_correct, axis=1)
    analysis_df['price_pct'] = analysis_df['kalshi_price'] / 100
    
    print(f"✅ Analysis complete: {len(analysis_df)} markets with weather data")
    
    return analysis_df

def create_comparison_report(analysis_df: pd.DataFrame) -> None:
    """Generate comprehensive comparison report"""
    
    print("\n" + "="*80)
    print("📊 KALSHI vs WEATHER DATA COMPARISON REPORT")
    print("="*80)
    
    if len(analysis_df) == 0:
        print("❌ No overlapping data for analysis")
        return
    
    total_markets = len(analysis_df)
    correct_predictions = analysis_df['prediction_correct'].sum()
    accuracy = correct_predictions / total_markets
    
    print(f"\n📈 OVERVIEW:")
    print(f"  Total analyzed markets: {total_markets}")
    print(f"  Date range: {analysis_df['date'].min()} to {analysis_df['date'].max()}")
    print(f"  Market prediction accuracy: {correct_predictions}/{total_markets} ({accuracy:.1%})")
    
    # Temperature statistics
    print(f"\n🌡️ TEMPERATURE ANALYSIS:")
    print(f"  Actual temp range: {analysis_df['best_temp'].min():.1f}°F to {analysis_df['best_temp'].max():.1f}°F")
    print(f"  Average actual temp: {analysis_df['best_temp'].mean():.1f}°F")
    print(f"  Temperature std dev: {analysis_df['best_temp'].std():.1f}°F")
    
    # Market performance
    won_markets = analysis_df[analysis_df['market_won']]
    lost_markets = analysis_df[~analysis_df['market_won']]
    
    print(f"\n💰 MARKET PERFORMANCE:")
    print(f"  Markets that resolved 'Yes': {len(won_markets)}/{total_markets} ({len(won_markets)/total_markets:.1%})")
    print(f"  Average price of winning markets: ${won_markets['kalshi_price'].mean()/100:.2f}")
    print(f"  Average price of losing markets: ${lost_markets['kalshi_price'].mean()/100:.2f}")
    
    # Accuracy by price ranges
    print(f"\n🎯 ACCURACY BY PRICE RANGE:")
    
    # Low priced markets (< $0.10)
    low_price = analysis_df[analysis_df['price_pct'] < 0.10]
    if len(low_price) > 0:
        low_accuracy = low_price['prediction_correct'].mean()
        print(f"  Low price markets (<$0.10): {low_accuracy:.1%} accuracy ({len(low_price)} markets)")
    
    # Medium priced markets ($0.10 - $0.90)
    med_price = analysis_df[(analysis_df['price_pct'] >= 0.10) & (analysis_df['price_pct'] <= 0.90)]
    if len(med_price) > 0:
        med_accuracy = med_price['prediction_correct'].mean()
        print(f"  Medium price markets ($0.10-$0.90): {med_accuracy:.1%} accuracy ({len(med_price)} markets)")
    
    # High priced markets (> $0.90)
    high_price = analysis_df[analysis_df['price_pct'] > 0.90]
    if len(high_price) > 0:
        high_accuracy = high_price['prediction_correct'].mean()
        print(f"  High price markets (>$0.90): {high_accuracy:.1%} accuracy ({len(high_price)} markets)")
    
    # Recent daily breakdown
    print(f"\n📅 RECENT RESULTS (Last 15 days):")
    recent = analysis_df.nlargest(15, 'date')
    
    for _, row in recent.iterrows():
        won_emoji = "✅" if row['market_won'] else "❌"
        correct_emoji = "🎯" if row['prediction_correct'] else "❗"
        price_str = f"${row['kalshi_price']/100:.2f}"
        temp_str = f"{row['best_temp']:.1f}°F"
        
        print(f"  {row['date']} {won_emoji}{correct_emoji}: {row['subtitle'][:25]}... → {temp_str} ({price_str})")
    
    print(f"\n🏆 KEY INSIGHTS:")
    
    # Market efficiency insights
    if accuracy > 0.6:
        print(f"  ✅ Markets show good predictive accuracy ({accuracy:.1%})")
    else:
        print(f"  ⚠️ Markets show low predictive accuracy ({accuracy:.1%})")
    
    # Price vs accuracy correlation
    if len(high_price) > 0 and len(low_price) > 0:
        if high_price['prediction_correct'].mean() > low_price['prediction_correct'].mean():
            print(f"  💡 Higher priced markets are more accurate (as expected)")
        else:
            print(f"  ⚠️ Price doesn't correlate with accuracy (market inefficiency?)")
    
    print(f"\n" + "="*80)

def main():
    """Main analysis function"""
    
    print("🚀 Starting Simple Kalshi vs Weather Comparison")
    print("="*60)
    
    # Load Kalshi data
    kalshi_df = load_kalshi_data()
    if kalshi_df.empty:
        return
    
    # Determine date range from settled Kalshi markets
    settled_markets = kalshi_df[kalshi_df['status'] == 'finalized']
    if settled_markets.empty:
        print("❌ No settled Kalshi markets found")
        return
    
    dates = []
    for ticker in settled_markets['event_ticker'].unique():
        market_date = extract_date_from_ticker(ticker)
        if market_date:
            dates.append(market_date)
    
    if not dates:
        print("❌ Could not extract dates from Kalshi tickers")
        return
    
    # Focus on recent period where we have good weather data
    end_date = max(dates)
    start_date = max(min(dates), end_date - timedelta(days=45))  # Last 45 days max
    
    print(f"📅 Analyzing period: {start_date} to {end_date}")
    
    # Get weather data
    weather_df = get_weather_data_for_date_range(start_date, end_date)
    
    # Analyze accuracy
    analysis_df = analyze_kalshi_accuracy(kalshi_df, weather_df)
    
    # Save detailed results
    if not analysis_df.empty:
        filename = 'kalshi_vs_weather_simple_analysis.csv'
        analysis_df.to_csv(filename, index=False)
        print(f"💾 Analysis saved to {filename}")
    
    # Generate report
    create_comparison_report(analysis_df)
    
    print("\n🎉 Analysis complete!")

if __name__ == "__main__":
    main()