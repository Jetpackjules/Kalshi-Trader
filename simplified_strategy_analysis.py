#!/usr/bin/env python3
"""
Simplified Kalshi Temperature Market Strategy Analysis
Analyzes strategies using available candlestick data without weather API calls.
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import os

class SimplifiedStrategyAnalyzer:
    def __init__(self):
        self.candlestick_data = None
        
    def load_data(self):
        """Load historical market data."""
        # Try main location first
        csv_paths = [
            "data/candles/KXHIGHNY_candles_5m.csv",
            "BACKLOG!/data/candles/KXHIGHNY_candles_5m.csv"
        ]
        
        for csv_path in csv_paths:
            if os.path.exists(csv_path):
                self.candlestick_data = pd.read_csv(csv_path)
                break
        
        if self.candlestick_data is None:
            raise FileNotFoundError("No candlestick data found")
            
        # Clean and prepare data
        self.candlestick_data['start'] = pd.to_datetime(self.candlestick_data['start'])
        self.candlestick_data['date'] = self.candlestick_data['start'].dt.date
        
        # Extract contract information
        self.candlestick_data['strike_temp'] = self.candlestick_data['ticker'].str.extract(r'[BT](\d+(?:\.\d+)?)')
        self.candlestick_data['strike_temp'] = pd.to_numeric(self.candlestick_data['strike_temp'])
        self.candlestick_data['contract_type'] = self.candlestick_data['ticker'].str.extract(r'-([BT])')
        
        # Parse contract dates from ticker (e.g., KXHIGHNY-25JUL19-B79.5)
        date_part = self.candlestick_data['ticker'].str.extract(r'25([A-Z]{3}\d{2})')
        self.candlestick_data['contract_date_str'] = '25' + date_part[0]
        
        print(f"Loaded {len(self.candlestick_data)} candlestick records")
        print(f"Date range: {self.candlestick_data['start'].min()} to {self.candlestick_data['start'].max()}")
        print(f"Unique tickers: {self.candlestick_data['ticker'].nunique()}")
        
        return self.candlestick_data
    
    def parse_contract_date(self, ticker):
        """Parse contract date from ticker."""
        try:
            # Extract date part (e.g., 25JUL19 from KXHIGHNY-25JUL19-B79.5)
            parts = ticker.split('-')
            if len(parts) < 2:
                return None
                
            date_str = parts[1]  # 25JUL19
            year = 2000 + int(date_str[:2])  # 2025
            month_str = date_str[2:5]  # JUL
            day = int(date_str[5:])  # 19
            
            month_map = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }
            
            return datetime(year, month_map[month_str], day).date()
        except:
            return None
    
    def analyze_cheap_no_strategy(self, max_price_cents=5):
        """
        Analyze the performance of buying cheap NO positions.
        Since we don't have real settlement data, we'll simulate based on price movements.
        """
        print(f"\n=== CHEAP NO STRATEGY ANALYSIS (≤{max_price_cents} cents) ===")
        
        # Get contract-level data
        contracts = []
        
        for ticker in self.candlestick_data['ticker'].unique():
            ticker_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            ticker_data = ticker_data.sort_values('start')
            
            if len(ticker_data) == 0:
                continue
                
            contract_date = self.parse_contract_date(ticker)
            strike_temp = ticker_data['strike_temp'].iloc[0]
            contract_type = ticker_data['contract_type'].iloc[0]
            
            # Find opportunities where NO price ≤ max_price_cents
            # NO price ≈ 100 - YES price
            ticker_data['no_price'] = 100 - ticker_data['close']
            cheap_opportunities = ticker_data[ticker_data['no_price'] <= max_price_cents]
            
            if len(cheap_opportunities) > 0:
                first_opportunity = cheap_opportunities.iloc[0]
                entry_price = first_opportunity['no_price']
                
                # Simulate settlement based on final market price
                final_price = ticker_data['close'].iloc[-1]
                
                # If final YES price < 50, assume NO wins (simplified)
                settled_no = final_price < 50
                
                pnl = (100 - entry_price) if settled_no else -entry_price
                
                contracts.append({
                    'ticker': ticker,
                    'contract_date': contract_date,
                    'strike_temp': strike_temp,
                    'contract_type': contract_type,
                    'entry_price': entry_price,
                    'final_market_price': final_price,
                    'settled_no': settled_no,
                    'pnl': pnl,
                    'roi_percent': (pnl / entry_price) * 100
                })
        
        if not contracts:
            return {'strategy': 'Cheap NO', 'total_trades': 0, 'message': 'No opportunities found'}
        
        df = pd.DataFrame(contracts)
        total_invested = df['entry_price'].sum()
        total_pnl = df['pnl'].sum()
        win_rate = (df['pnl'] > 0).mean()
        
        return {
            'strategy': 'Cheap NO Orders',
            'params': {'max_price_cents': max_price_cents},
            'total_trades': len(contracts),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': win_rate,
            'avg_entry_price': df['entry_price'].mean(),
            'avg_pnl_per_trade': df['pnl'].mean(),
            'details': contracts[:10]  # Show first 10 trades
        }
    
    def analyze_momentum_strategy(self, lookback_hours=24, momentum_threshold=10):
        """
        Analyze momentum-based strategy using price movements.
        Buy when there's strong momentum in one direction.
        """
        print(f"\n=== MOMENTUM STRATEGY ANALYSIS ===")
        
        trades = []
        
        for ticker in self.candlestick_data['ticker'].unique():
            ticker_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            ticker_data = ticker_data.sort_values('start')
            
            if len(ticker_data) < 5:  # Need enough data points
                continue
            
            # Calculate price momentum over lookback period
            for i in range(len(ticker_data)):
                current_row = ticker_data.iloc[i]
                current_time = current_row['start']
                current_price = current_row['close']
                
                # Look back 'lookback_hours' hours
                lookback_time = current_time - pd.Timedelta(hours=lookback_hours)
                historical_data = ticker_data[ticker_data['start'] >= lookback_time]
                historical_data = historical_data[historical_data['start'] < current_time]
                
                if len(historical_data) < 2:
                    continue
                
                # Calculate momentum (price change over period)
                start_price = historical_data['close'].iloc[0]
                momentum = current_price - start_price
                
                # Trade if momentum exceeds threshold
                if abs(momentum) >= momentum_threshold:
                    # Determine trade direction
                    if momentum > 0:
                        # Upward momentum, buy YES
                        side = 'YES'
                        entry_price = current_price
                    else:
                        # Downward momentum, buy NO
                        side = 'NO' 
                        entry_price = 100 - current_price
                    
                    # Simulate exit at final price
                    final_price = ticker_data['close'].iloc[-1]
                    
                    if side == 'YES':
                        settled_yes = final_price > 50  # Simplified
                        pnl = (100 - entry_price) if settled_yes else -entry_price
                    else:
                        settled_yes = final_price > 50
                        pnl = (100 - entry_price) if not settled_yes else -entry_price
                    
                    trades.append({
                        'ticker': ticker,
                        'trade_time': current_time,
                        'side': side,
                        'momentum': momentum,
                        'entry_price': entry_price,
                        'final_price': final_price,
                        'pnl': pnl
                    })
                    
                    break  # One trade per contract
        
        if not trades:
            return {'strategy': 'Momentum', 'total_trades': 0, 'message': 'No momentum signals found'}
        
        df = pd.DataFrame(trades)
        total_invested = df['entry_price'].sum()
        total_pnl = df['pnl'].sum()
        win_rate = (df['pnl'] > 0).mean()
        
        return {
            'strategy': 'Momentum Trading',
            'params': {'lookback_hours': lookback_hours, 'momentum_threshold': momentum_threshold},
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': win_rate,
            'avg_momentum': df['momentum'].mean(),
            'details': trades[:10]
        }
    
    def analyze_contrarian_strategy(self, extreme_price_threshold=85):
        """
        Contrarian strategy: bet against extreme prices.
        Buy NO when YES price is very high, buy YES when very low.
        """
        print(f"\n=== CONTRARIAN STRATEGY ANALYSIS ===")
        
        trades = []
        
        for ticker in self.candlestick_data['ticker'].unique():
            ticker_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            ticker_data = ticker_data.sort_values('start')
            
            if len(ticker_data) == 0:
                continue
                
            # Look for extreme prices
            for _, row in ticker_data.iterrows():
                price = row['close']
                
                if price >= extreme_price_threshold:
                    # Very high YES price, buy NO
                    side = 'NO'
                    entry_price = 100 - price
                elif price <= (100 - extreme_price_threshold):
                    # Very low YES price, buy YES
                    side = 'YES'
                    entry_price = price
                else:
                    continue
                
                # Simulate settlement
                final_price = ticker_data['close'].iloc[-1]
                settled_yes = final_price > 50
                
                if (side == 'YES' and settled_yes) or (side == 'NO' and not settled_yes):
                    pnl = 100 - entry_price
                else:
                    pnl = -entry_price
                
                trades.append({
                    'ticker': ticker,
                    'side': side,
                    'entry_price': entry_price,
                    'market_price': price,
                    'final_price': final_price,
                    'pnl': pnl
                })
                
                break  # One trade per contract
        
        if not trades:
            return {'strategy': 'Contrarian', 'total_trades': 0, 'message': 'No extreme prices found'}
        
        df = pd.DataFrame(trades)
        total_invested = df['entry_price'].sum()
        total_pnl = df['pnl'].sum()
        win_rate = (df['pnl'] > 0).mean()
        
        return {
            'strategy': 'Contrarian Trading',
            'params': {'extreme_price_threshold': extreme_price_threshold},
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': win_rate,
            'details': trades[:10]
        }
    
    def analyze_market_stats(self):
        """Analyze basic market statistics."""
        print(f"\n=== MARKET STATISTICS ===")
        
        stats = {}
        
        # Price distribution
        stats['price_stats'] = {
            'mean': self.candlestick_data['close'].mean(),
            'median': self.candlestick_data['close'].median(),
            'std': self.candlestick_data['close'].std(),
            'min': self.candlestick_data['close'].min(),
            'max': self.candlestick_data['close'].max()
        }
        
        # Volume/count analysis
        stats['volume_stats'] = {
            'mean_count': self.candlestick_data['count'].mean(),
            'total_count': self.candlestick_data['count'].sum()
        }
        
        # Contract type distribution
        type_dist = self.candlestick_data['contract_type'].value_counts()
        stats['contract_types'] = type_dist.to_dict()
        
        # Price ranges
        cheap_prices = (self.candlestick_data['close'] <= 5).sum()
        expensive_prices = (self.candlestick_data['close'] >= 85).sum()
        
        stats['price_distribution'] = {
            'very_cheap_count': cheap_prices,
            'very_expensive_count': expensive_prices,
            'cheap_percentage': (cheap_prices / len(self.candlestick_data)) * 100,
            'expensive_percentage': (expensive_prices / len(self.candlestick_data)) * 100
        }
        
        return stats
    
    def run_analysis(self):
        """Run complete analysis of all strategies."""
        print("=" * 80)
        print("SIMPLIFIED KALSHI TEMPERATURE MARKET STRATEGY ANALYSIS")
        print("=" * 80)
        
        # Load data
        self.load_data()
        
        # Market statistics
        market_stats = self.analyze_market_stats()
        
        print(f"Market Statistics:")
        print(f"  Average Price: ${market_stats['price_stats']['mean']:.2f}")
        print(f"  Price Range: ${market_stats['price_stats']['min']:.1f} - ${market_stats['price_stats']['max']:.1f}")
        print(f"  Cheap Prices (≤$5): {market_stats['price_distribution']['cheap_percentage']:.1f}%")
        print(f"  Expensive Prices (≥$85): {market_stats['price_distribution']['expensive_percentage']:.1f}%")
        
        # Test different strategies
        strategies = [
            # Cheap NO strategies
            lambda: self.analyze_cheap_no_strategy(2),
            lambda: self.analyze_cheap_no_strategy(5), 
            lambda: self.analyze_cheap_no_strategy(10),
            
            # Momentum strategies
            lambda: self.analyze_momentum_strategy(24, 5),
            lambda: self.analyze_momentum_strategy(12, 10),
            
            # Contrarian strategies
            lambda: self.analyze_contrarian_strategy(80),
            lambda: self.analyze_contrarian_strategy(90),
        ]
        
        results = []
        for strategy_func in strategies:
            try:
                result = strategy_func()
                results.append(result)
                
                if 'message' in result:
                    print(f"\n{result['strategy']}: {result['message']}")
                else:
                    print(f"\n{result['strategy']} {result.get('params', '')}")
                    print(f"  Trades: {result['total_trades']}")
                    print(f"  Total Invested: ${result['total_invested']:.2f}")
                    print(f"  Total PnL: ${result['total_pnl']:.2f}")
                    print(f"  ROI: {result['roi_percent']:.1f}%")
                    print(f"  Win Rate: {result['win_rate']:.1%}")
                    
            except Exception as e:
                print(f"Error in strategy analysis: {e}")
        
        # Sort by ROI
        successful_results = [r for r in results if r.get('total_trades', 0) > 0]
        successful_results.sort(key=lambda x: x.get('roi_percent', 0), reverse=True)
        
        print("\n" + "=" * 80)
        print("STRATEGY PERFORMANCE RANKING")
        print("=" * 80)
        
        if successful_results:
            for i, result in enumerate(successful_results, 1):
                print(f"{i:2d}. {result['strategy']}")
                if 'params' in result:
                    print(f"     Params: {result['params']}")
                print(f"     ROI: {result['roi_percent']:8.1f}% | Win Rate: {result['win_rate']:5.1%} | "
                      f"Trades: {result['total_trades']:3d} | PnL: ${result['total_pnl']:8.2f}")
        else:
            print("No successful strategies found with the current data.")
        
        # Save results
        output_file = f"simplified_strategy_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                'market_stats': market_stats,
                'strategy_results': results
            }, f, indent=2, default=str)
        
        print(f"\nDetailed results saved to: {output_file}")
        
        return results, market_stats

def main():
    analyzer = SimplifiedStrategyAnalyzer()
    return analyzer.run_analysis()

if __name__ == "__main__":
    main()