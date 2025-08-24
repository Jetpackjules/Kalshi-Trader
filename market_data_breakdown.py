#!/usr/bin/env python3
"""
Create a nice breakdown of our market API data with graphs for each contract.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import os

def load_and_analyze_market_data():
    """Load market data and create breakdown with graphs."""
    
    # Load the candlestick data
    df = pd.read_csv('BACKLOG!/data/candles/KXHIGHNY_candles_5m.csv')
    df['start'] = pd.to_datetime(df['start'])
    
    print("🔍 KALSHI MARKET DATA BREAKDOWN")
    print("=" * 60)
    
    # Focus on July 27 contracts (we have good data for these)
    july27_tickers = [ticker for ticker in df['ticker'].unique() if '25JUL27' in ticker]
    
    print(f"Found {len(july27_tickers)} July 27 contracts:")
    for ticker in sorted(july27_tickers):
        print(f"  • {ticker}")
    
    # Create output directory for graphs
    os.makedirs('market_graphs', exist_ok=True)
    
    # Analyze each contract
    contract_summaries = []
    
    for ticker in sorted(july27_tickers):
        print(f"\n📈 ANALYZING {ticker}")
        print("-" * 50)
        
        # Get contract data
        contract_data = df[df['ticker'] == ticker].copy()
        contract_data = contract_data.sort_values('start')
        
        if len(contract_data) == 0:
            print("  No data found!")
            continue
        
        # Extract contract info
        if '-B' in ticker:
            strike_temp = float(ticker.split('-B')[1])
            contract_type = 'BELOW'
            contract_desc = f"Temp will be BELOW {strike_temp}°F"
        elif '-T' in ticker:
            strike_temp = float(ticker.split('-T')[1])
            contract_type = 'ABOVE'
            contract_desc = f"Temp will be ABOVE {strike_temp}°F"
        else:
            continue
        
        # Calculate stats
        first_price = contract_data['close'].iloc[0]
        last_price = contract_data['close'].iloc[-1]
        min_price = contract_data['close'].min()
        max_price = contract_data['close'].max()
        avg_price = contract_data['close'].mean()
        
        trading_start = contract_data['start'].iloc[0]
        trading_end = contract_data['start'].iloc[-1]
        total_trades = contract_data['count'].sum()
        
        # Print summary
        print(f"  📋 CONTRACT: {contract_desc}")
        print(f"  ⏰ TRADING: {trading_start.strftime('%m/%d %H:%M')} → {trading_end.strftime('%m/%d %H:%M')}")
        print(f"  💰 PRICES: {first_price:.0f}¢ → {last_price:.0f}¢ (Range: {min_price:.0f}¢-{max_price:.0f}¢)")
        print(f"  📊 AVERAGE: {avg_price:.1f}¢, TRADES: {total_trades}")
        
        # Create graph
        plt.figure(figsize=(12, 6))
        
        # Plot price over time
        plt.subplot(1, 2, 1)
        plt.plot(contract_data['start'], contract_data['close'], 'b-', linewidth=2, label='Price')
        plt.fill_between(contract_data['start'], contract_data['low'], contract_data['high'], 
                        alpha=0.3, color='lightblue', label='High-Low Range')
        
        plt.title(f'{ticker}\n{contract_desc}')
        plt.xlabel('Time')
        plt.ylabel('Price (¢)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.xticks(rotation=45)
        
        # Add key annotations
        plt.annotate(f'Start: {first_price:.0f}¢', 
                    xy=(contract_data['start'].iloc[0], first_price),
                    xytext=(10, 10), textcoords='offset points',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        
        plt.annotate(f'End: {last_price:.0f}¢', 
                    xy=(contract_data['start'].iloc[-1], last_price),
                    xytext=(-50, 10), textcoords='offset points',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='orange', alpha=0.7),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        
        # Plot trading volume over time
        plt.subplot(1, 2, 2)
        plt.bar(contract_data['start'], contract_data['count'], 
               width=pd.Timedelta(minutes=3), alpha=0.7, color='green')
        plt.title('Trading Volume')
        plt.xlabel('Time')
        plt.ylabel('Trades per 5min')
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        # Save graph
        safe_ticker = ticker.replace(':', '_').replace('-', '_')
        plt.savefig(f'market_graphs/{safe_ticker}_analysis.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"  💾 SAVED: market_graphs/{safe_ticker}_analysis.png")
        
        # Store for summary
        contract_summaries.append({
            'ticker': ticker,
            'contract_type': contract_type,
            'strike_temp': strike_temp,
            'first_price': first_price,
            'last_price': last_price,
            'min_price': min_price,
            'max_price': max_price,
            'avg_price': avg_price,
            'total_trades': total_trades,
            'price_change': last_price - first_price,
            'price_change_pct': ((last_price - first_price) / first_price * 100) if first_price > 0 else 0
        })
    
    # Create summary comparison
    if contract_summaries:
        print(f"\n📊 JULY 27 CONTRACTS SUMMARY")
        print("=" * 60)
        
        df_summary = pd.DataFrame(contract_summaries)
        
        # Sort by strike temperature
        df_summary = df_summary.sort_values('strike_temp')
        
        print("Contract                   Type    Strike  Start→End    Change    Trades")
        print("-" * 70)
        for _, row in df_summary.iterrows():
            ticker_short = row['ticker'].split('-')[-1]  # Just the strike part
            change_sign = "+" if row['price_change'] >= 0 else ""
            print(f"{ticker_short:<25} {row['contract_type']:<6} {row['strike_temp']:>6.1f}°F "
                  f"{row['first_price']:>3.0f}¢→{row['last_price']:>3.0f}¢  "
                  f"{change_sign}{row['price_change']:>4.0f}¢({row['price_change_pct']:>+4.0f}%)  "
                  f"{row['total_trades']:>6.0f}")
        
        # Create overview graph
        plt.figure(figsize=(14, 8))
        
        # Subplot 1: Strike prices vs final market prices
        plt.subplot(2, 2, 1)
        below_contracts = df_summary[df_summary['contract_type'] == 'BELOW']
        above_contracts = df_summary[df_summary['contract_type'] == 'ABOVE']
        
        if len(below_contracts) > 0:
            plt.scatter(below_contracts['strike_temp'], below_contracts['last_price'], 
                       s=100, c='red', label='BELOW contracts', alpha=0.7)
        if len(above_contracts) > 0:
            plt.scatter(above_contracts['strike_temp'], above_contracts['last_price'], 
                       s=100, c='blue', label='ABOVE contracts', alpha=0.7)
        
        plt.xlabel('Strike Temperature (°F)')
        plt.ylabel('Final Price (¢)')
        plt.title('Final Prices by Strike Temperature')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Add actual temperature line if we can estimate it
        # Based on final prices, we can estimate where settlement occurred
        plt.axvline(x=78.5, color='green', linestyle='--', alpha=0.7, label='Estimated Actual Temp')
        
        # Subplot 2: Price changes
        plt.subplot(2, 2, 2)
        colors = ['red' if ct == 'BELOW' else 'blue' for ct in df_summary['contract_type']]
        bars = plt.bar(range(len(df_summary)), df_summary['price_change'], color=colors, alpha=0.7)
        plt.xlabel('Contract')
        plt.ylabel('Price Change (¢)')
        plt.title('Price Changes During Trading')
        plt.xticks(range(len(df_summary)), 
                  [f"{row['contract_type'][0]}{row['strike_temp']:.0f}" for _, row in df_summary.iterrows()],
                  rotation=45)
        plt.grid(True, alpha=0.3)
        plt.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        
        # Subplot 3: Trading volume
        plt.subplot(2, 2, 3)
        plt.bar(range(len(df_summary)), df_summary['total_trades'], color=colors, alpha=0.7)
        plt.xlabel('Contract')
        plt.ylabel('Total Trades')
        plt.title('Trading Volume by Contract')
        plt.xticks(range(len(df_summary)), 
                  [f"{row['contract_type'][0]}{row['strike_temp']:.0f}" for _, row in df_summary.iterrows()],
                  rotation=45)
        plt.grid(True, alpha=0.3)
        
        # Subplot 4: Price volatility (range)
        plt.subplot(2, 2, 4)
        volatility = df_summary['max_price'] - df_summary['min_price']
        plt.bar(range(len(df_summary)), volatility, color=colors, alpha=0.7)
        plt.xlabel('Contract')
        plt.ylabel('Price Range (¢)')
        plt.title('Price Volatility (Max - Min)')
        plt.xticks(range(len(df_summary)), 
                  [f"{row['contract_type'][0]}{row['strike_temp']:.0f}" for _, row in df_summary.iterrows()],
                  rotation=45)
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('market_graphs/OVERVIEW_july27_contracts.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"\n💾 OVERVIEW SAVED: market_graphs/OVERVIEW_july27_contracts.png")
        
        # Market insights
        print(f"\n🧠 MARKET INSIGHTS")
        print("-" * 30)
        
        # Estimate actual temperature from settlement prices
        high_final_prices = df_summary[df_summary['last_price'] > 80]
        low_final_prices = df_summary[df_summary['last_price'] < 20]
        
        if len(high_final_prices) > 0:
            settled_yes_contracts = high_final_prices[['ticker', 'contract_type', 'strike_temp', 'last_price']]
            print("Contracts that likely settled YES (>80¢):")
            for _, row in settled_yes_contracts.iterrows():
                print(f"  • {row['ticker']}: {row['last_price']:.0f}¢")
        
        if len(low_final_prices) > 0:
            settled_no_contracts = low_final_prices[['ticker', 'contract_type', 'strike_temp', 'last_price']]
            print("Contracts that likely settled NO (<20¢):")
            for _, row in settled_no_contracts.iterrows():
                print(f"  • {row['ticker']}: {row['last_price']:.0f}¢")
        
        # Trading opportunities analysis
        big_movers = df_summary[abs(df_summary['price_change']) > 30]
        if len(big_movers) > 0:
            print(f"\nBiggest price movers (>30¢ change):")
            for _, row in big_movers.iterrows():
                direction = "📈" if row['price_change'] > 0 else "📉"
                print(f"  {direction} {row['ticker']}: {row['price_change']:+.0f}¢ ({row['price_change_pct']:+.0f}%)")
    
    print(f"\n✅ Analysis complete! Check the market_graphs/ folder for all visualizations.")
    return contract_summaries

if __name__ == "__main__":
    load_and_analyze_market_data()