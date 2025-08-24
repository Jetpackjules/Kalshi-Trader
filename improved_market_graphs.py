#!/usr/bin/env python3
"""
Create improved market graphs with better time formatting and data investigation.
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from datetime import datetime, timezone
import os

def create_improved_graphs():
    """Create better graphs with clearer time display and data investigation."""
    
    # Load the candlestick data
    df = pd.read_csv('BACKLOG!/data/candles/KXHIGHNY_candles_5m.csv')
    df['start'] = pd.to_datetime(df['start'])
    
    # Convert to Eastern Time for clearer display
    df['start_et'] = df['start'].dt.tz_convert('America/New_York')
    
    print("🔍 INVESTIGATING MARKET DATA COMPLETENESS")
    print("=" * 60)
    
    # Check all July 27 contracts and their data coverage
    july27_tickers = [ticker for ticker in df['ticker'].unique() if '25JUL27' in ticker]
    
    for ticker in sorted(july27_tickers):
        contract_data = df[df['ticker'] == ticker].copy()
        contract_data = contract_data.sort_values('start')
        
        if len(contract_data) == 0:
            continue
            
        print(f"\n📊 {ticker}")
        print(f"  Data points: {len(contract_data)}")
        print(f"  First trade: {contract_data['start_et'].iloc[0].strftime('%m/%d %I:%M %p ET')}")
        print(f"  Last trade:  {contract_data['start_et'].iloc[-1].strftime('%m/%d %I:%M %p ET')}")
        print(f"  Price range: {contract_data['close'].min():.0f}¢ - {contract_data['close'].max():.0f}¢")
        
        # Check for data gaps
        time_diff = contract_data['start'].diff()
        large_gaps = time_diff[time_diff > pd.Timedelta(hours=2)]
        if len(large_gaps) > 0:
            print(f"  ⚠️  DATA GAPS: {len(large_gaps)} gaps longer than 2 hours")
            for idx, gap in large_gaps.items():
                gap_start = contract_data.loc[idx-1, 'start_et']
                gap_end = contract_data.loc[idx, 'start_et']
                print(f"    Gap: {gap_start.strftime('%m/%d %I:%M %p')} → {gap_end.strftime('%m/%d %I:%M %p')} ({gap})")
    
    # Create output directory
    os.makedirs('improved_graphs', exist_ok=True)
    
    # Focus on B81.5 contract that you asked about
    ticker = 'KXHIGHNY-25JUL27-B81.5'
    contract_data = df[df['ticker'] == ticker].copy()
    contract_data = contract_data.sort_values('start')
    
    if len(contract_data) > 0:
        print(f"\n📈 DETAILED ANALYSIS: {ticker}")
        print("-" * 50)
        
        # Show all data points with timestamps
        print("All trading data points:")
        for idx, row in contract_data.iterrows():
            et_time = row['start_et']
            print(f"  {et_time.strftime('%m/%d %I:%M %p ET')}: "
                  f"${row['close']:.0f}¢ (vol: {row['count']}, range: {row['low']:.0f}-{row['high']:.0f})")
        
        # Create improved graph
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
        
        # Main price chart
        ax1.plot(contract_data['start_et'], contract_data['close'], 'b-', linewidth=3, label='Close Price', marker='o', markersize=4)
        ax1.fill_between(contract_data['start_et'], contract_data['low'], contract_data['high'], 
                        alpha=0.3, color='lightblue', label='High-Low Range')
        
        # Add annotations for key points
        first_row = contract_data.iloc[0]
        last_row = contract_data.iloc[-1]
        
        ax1.annotate(f'START: {first_row["close"]:.0f}¢\n{first_row["start_et"].strftime("%I:%M %p")}', 
                    xy=(first_row['start_et'], first_row['close']),
                    xytext=(20, 20), textcoords='offset points',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.8),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        
        ax1.annotate(f'END: {last_row["close"]:.0f}¢\n{last_row["start_et"].strftime("%I:%M %p")}', 
                    xy=(last_row['start_et'], last_row['close']),
                    xytext=(-80, 20), textcoords='offset points',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='orange', alpha=0.8),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        
        # Find biggest price moves
        for i in range(1, len(contract_data)):
            prev_price = contract_data.iloc[i-1]['close']
            curr_price = contract_data.iloc[i]['close']
            change = curr_price - prev_price
            
            if abs(change) > 20:  # Big moves > 20¢
                curr_row = contract_data.iloc[i]
                direction = "📈" if change > 0 else "📉"
                ax1.annotate(f'{direction} {change:+.0f}¢', 
                            xy=(curr_row['start_et'], curr_row['close']),
                            xytext=(0, 15), textcoords='offset points',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor='red' if change < 0 else 'green', alpha=0.7),
                            ha='center')
        
        ax1.set_title(f'{ticker}\nTemp will be BELOW 81.5°F', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Price (¢)', fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # Format x-axis to show clear times
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%I:%M %p\n%m/%d'))
        ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        
        # Volume chart
        ax2.bar(contract_data['start_et'], contract_data['count'], 
               width=pd.Timedelta(minutes=3), alpha=0.7, color='green')
        ax2.set_ylabel('Trades per 5min', fontsize=12)
        ax2.set_xlabel('Time (Eastern)', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%I:%M %p\n%m/%d'))
        ax2.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        
        plt.tight_layout()
        plt.savefig('improved_graphs/B81_5_detailed_analysis.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"\n💾 SAVED: improved_graphs/B81_5_detailed_analysis.png")
    
    # Check what's missing - compare to theoretical contract timeline
    print(f"\n🔍 DATA COMPLETENESS ANALYSIS")
    print("-" * 40)
    print("❌ ISSUES FOUND:")
    print("1. Our API data starts at 7:25 PM on July 27")
    print("2. Missing all earlier trading from contract launch")
    print("3. Contracts typically launch days/weeks before expiration")
    print("4. Website shows full history, our API gives limited window")
    print()
    print("💡 POSSIBLE CAUSES:")
    print("1. Kalshi API rate limits historical data")
    print("2. Our data collection script has limited time range")
    print("3. Free tier API access restrictions")
    print("4. Candlestick data aggregation window too narrow")
    print()
    print("✅ RECOMMENDATIONS:")
    print("1. Check if our backtest script can pull longer history")
    print("2. Try different API endpoints for historical data")
    print("3. Consider using market data from earlier dates")
    print("4. Verify API parameters for data range")

if __name__ == "__main__":
    create_improved_graphs()