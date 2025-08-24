#!/usr/bin/env python3
"""
Create full timeline graphs showing complete trading lifecycle from start to finish.
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from datetime import datetime, timedelta
import os

def create_full_timeline_graphs():
    """Create graphs with maximum timeline coverage."""
    
    # Load the candlestick data
    df = pd.read_csv('BACKLOG!/data/candles/KXHIGHNY_candles_5m.csv')
    df['start'] = pd.to_datetime(df['start'])
    df['start_et'] = df['start'].dt.tz_convert('America/New_York')
    
    print("🔍 FULL TIMELINE ANALYSIS - JULY 27 CONTRACTS")
    print("=" * 60)
    
    # Find all July 27 contracts and their complete data range
    july27_tickers = [ticker for ticker in df['ticker'].unique() if '25JUL27' in ticker]
    
    # Get the earliest and latest timestamps across all July 27 contracts
    all_july27_data = df[df['ticker'].isin(july27_tickers)]
    earliest_time = all_july27_data['start_et'].min()
    latest_time = all_july27_data['start_et'].max()
    
    print(f"Overall data range for July 27 contracts:")
    print(f"  Earliest: {earliest_time.strftime('%m/%d/%Y %I:%M %p ET')}")
    print(f"  Latest:   {latest_time.strftime('%m/%d/%Y %I:%M %p ET')}")
    print(f"  Duration: {latest_time - earliest_time}")
    
    # Create ideal timeline (what you suggested)
    july26_6am = pd.Timestamp('2025-07-26 06:00:00', tz='America/New_York')
    july28_6am = pd.Timestamp('2025-07-28 06:00:00', tz='America/New_York')
    
    print(f"\nDesired timeline:")
    print(f"  Start: {july26_6am.strftime('%m/%d/%Y %I:%M %p ET')}")
    print(f"  End:   {july28_6am.strftime('%m/%d/%Y %I:%M %p ET')}")
    print(f"  Duration: {july28_6am - july26_6am}")
    
    # Create output directory
    os.makedirs('full_timeline_graphs', exist_ok=True)
    
    # Analyze each contract's full timeline
    print(f"\nContract-by-contract analysis:")
    for ticker in sorted(july27_tickers):
        contract_data = df[df['ticker'] == ticker].copy()
        contract_data = contract_data.sort_values('start')
        
        if len(contract_data) == 0:
            print(f"  {ticker}: No data")
            continue
            
        first_trade = contract_data['start_et'].iloc[0]
        last_trade = contract_data['start_et'].iloc[-1]
        duration = last_trade - first_trade
        
        print(f"  {ticker}:")
        print(f"    First: {first_trade.strftime('%m/%d %I:%M %p ET')}")
        print(f"    Last:  {last_trade.strftime('%m/%d %I:%M %p ET')}")
        print(f"    Duration: {duration}")
        print(f"    Data points: {len(contract_data)}")
    
    # Create comprehensive overview graph with extended timeline
    fig, axes = plt.subplots(3, 2, figsize=(20, 16))
    axes = axes.flatten()
    
    # Set consistent x-axis range for all subplots
    x_start = min(earliest_time, july26_6am)
    x_end = max(latest_time, july28_6am)
    
    for i, ticker in enumerate(sorted(july27_tickers)):
        if i >= 6: break
        
        contract_data = df[df['ticker'] == ticker].sort_values('start')
        if len(contract_data) == 0: continue
        
        ax = axes[i]
        
        # Plot the actual data
        ax.plot(contract_data['start_et'], contract_data['close'], 'b-', linewidth=2, marker='o', markersize=3)
        ax.fill_between(contract_data['start_et'], contract_data['low'], contract_data['high'], 
                       alpha=0.2, color='lightblue')
        
        # Add key annotations
        first_row = contract_data.iloc[0]
        last_row = contract_data.iloc[-1]
        
        ax.annotate(f'START\n{first_row["close"]:.0f}¢\n{first_row["start_et"].strftime("%m/%d %I:%M %p")}', 
                   xy=(first_row['start_et'], first_row['close']),
                   xytext=(20, 20), textcoords='offset points', fontsize=9,
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.8),
                   arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        
        ax.annotate(f'END\n{last_row["close"]:.0f}¢\n{last_row["start_et"].strftime("%m/%d %I:%M %p")}', 
                   xy=(last_row['start_et'], last_row['close']),
                   xytext=(-80, 20), textcoords='offset points', fontsize=9,
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='orange', alpha=0.8),
                   arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        
        # Extract contract details
        if '-B' in ticker:
            strike_temp = float(ticker.split('-B')[1])
            contract_desc = f"BELOW {strike_temp}°F"
        elif '-T' in ticker:
            strike_temp = float(ticker.split('-T')[1])
            contract_desc = f"ABOVE {strike_temp}°F"
        else:
            contract_desc = ticker.split('-')[-1]
        
        ax.set_title(f'{ticker.split("-")[-1]}\n{contract_desc}', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # Set consistent x-axis range and formatting
        ax.set_xlim(x_start, x_end)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n%I %p'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
        ax.xaxis.set_minor_locator(mdates.HourLocator(interval=2))
        
        # Add vertical lines for key times
        july27_midnight = pd.Timestamp('2025-07-27 00:00:00', tz='America/New_York')
        july28_midnight = pd.Timestamp('2025-07-28 00:00:00', tz='America/New_York')
        
        ax.axvline(x=july27_midnight, color='red', linestyle='--', alpha=0.5, label='July 27 Start')
        ax.axvline(x=july28_midnight, color='green', linestyle='--', alpha=0.5, label='July 28 Start')
        
        # Rotate x-axis labels
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, fontsize=10)
        
        ax.set_ylabel('Price (¢)', fontsize=11)
        
        # Add data coverage indicator
        coverage_start = first_row['start_et']
        coverage_end = last_row['start_et']
        total_possible = july28_6am - july26_6am
        actual_coverage = coverage_end - coverage_start
        coverage_pct = (actual_coverage / total_possible) * 100
        
        ax.text(0.02, 0.98, f'Coverage: {coverage_pct:.1f}%\n({actual_coverage})', 
                transform=ax.transAxes, fontsize=9, verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    plt.suptitle('July 27 Temperature Contracts - Full Timeline Analysis\n(Red line = July 27 start, Green line = July 28 start)', 
                 fontsize=16, fontweight='bold')
    plt.tight_layout()
    plt.savefig('full_timeline_graphs/COMPLETE_july27_timeline.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"\n💾 SAVED: full_timeline_graphs/COMPLETE_july27_timeline.png")
    
    # Create individual detailed graphs for each contract
    for ticker in sorted(july27_tickers):
        contract_data = df[df['ticker'] == ticker].sort_values('start')
        if len(contract_data) == 0: continue
        
        # Create detailed individual graph
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10))
        
        # Price chart
        ax1.plot(contract_data['start_et'], contract_data['close'], 'b-', linewidth=3, marker='o', markersize=4)
        ax1.fill_between(contract_data['start_et'], contract_data['low'], contract_data['high'], 
                        alpha=0.3, color='lightblue', label='High-Low Range')
        
        # Add detailed annotations for all major price changes
        for i in range(len(contract_data)):
            row = contract_data.iloc[i]
            if i == 0:  # First point
                ax1.annotate(f'START: {row["close"]:.0f}¢', 
                           xy=(row['start_et'], row['close']),
                           xytext=(10, 20), textcoords='offset points',
                           bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.8),
                           arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
            elif i == len(contract_data) - 1:  # Last point
                ax1.annotate(f'END: {row["close"]:.0f}¢', 
                           xy=(row['start_et'], row['close']),
                           xytext=(-60, 20), textcoords='offset points',
                           bbox=dict(boxstyle='round,pad=0.5', facecolor='orange', alpha=0.8),
                           arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
            elif i > 0:  # Check for big price moves
                prev_price = contract_data.iloc[i-1]['close']
                curr_price = row['close']
                change = curr_price - prev_price
                
                if abs(change) > 15:  # Big moves > 15¢
                    direction = "📈" if change > 0 else "📉"
                    ax1.annotate(f'{direction}{change:+.0f}¢', 
                               xy=(row['start_et'], row['close']),
                               xytext=(0, 15), textcoords='offset points',
                               bbox=dict(boxstyle='round,pad=0.3', 
                                        facecolor='green' if change > 0 else 'red', alpha=0.7),
                               ha='center', fontsize=9)
        
        # Extract contract details for title
        if '-B' in ticker:
            strike_temp = float(ticker.split('-B')[1])
            contract_desc = f"Temperature will be BELOW {strike_temp}°F"
        elif '-T' in ticker:
            strike_temp = float(ticker.split('-T')[1])
            contract_desc = f"Temperature will be ABOVE {strike_temp}°F"
        else:
            contract_desc = ticker
        
        ax1.set_title(f'{ticker}\n{contract_desc}', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Price (¢)', fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # Set x-axis range to show full context
        ax1.set_xlim(x_start, x_end)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %I:%M %p'))
        ax1.xaxis.set_major_locator(mdates.HourLocator(interval=4))
        
        # Add key time markers
        ax1.axvline(x=july27_midnight, color='red', linestyle='--', alpha=0.7, label='July 27 Start')
        ax1.axvline(x=july28_midnight, color='green', linestyle='--', alpha=0.7, label='July 28 Start')
        
        # Volume chart
        ax2.bar(contract_data['start_et'], contract_data['count'], 
               width=pd.Timedelta(minutes=3), alpha=0.7, color='green')
        ax2.set_ylabel('Trades per 5min', fontsize=12)
        ax2.set_xlabel('Time (Eastern)', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.set_xlim(x_start, x_end)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %I:%M %p'))
        ax2.xaxis.set_major_locator(mdates.HourLocator(interval=4))
        
        plt.tight_layout()
        
        # Save individual contract graph
        safe_ticker = ticker.replace(':', '_').replace('-', '_')
        plt.savefig(f'full_timeline_graphs/{safe_ticker}_full_timeline.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"💾 SAVED: full_timeline_graphs/{safe_ticker}_full_timeline.png")
    
    # Summary of data gaps
    print(f"\n📊 DATA COVERAGE ANALYSIS")
    print("-" * 40)
    
    total_desired = july28_6am - july26_6am
    actual_coverage = latest_time - earliest_time
    coverage_pct = (actual_coverage / total_desired) * 100
    
    print(f"Desired coverage: {total_desired} (48 hours)")
    print(f"Actual coverage:  {actual_coverage} ({coverage_pct:.1f}%)")
    print(f"Missing time:     {total_desired - actual_coverage}")
    
    # Calculate gaps
    missing_start = earliest_time - july26_6am
    missing_end = july28_6am - latest_time
    
    if missing_start > pd.Timedelta(0):
        print(f"Missing from start: {missing_start}")
    if missing_end > pd.Timedelta(0):
        print(f"Missing from end: {missing_end}")
    
    print(f"\n✅ All full timeline graphs saved to: full_timeline_graphs/")

if __name__ == "__main__":
    create_full_timeline_graphs()