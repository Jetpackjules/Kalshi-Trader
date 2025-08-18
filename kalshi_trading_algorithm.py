#!/usr/bin/env python3
"""
Kalshi Temperature Trading Algorithm
Analyzes market inefficiencies and provides buy/no recommendations
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import logging
from typing import Dict, List, Tuple, Optional
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KalshiTradingAlgorithm:
    """
    Advanced trading algorithm for Kalshi temperature markets
    Analyzes market inefficiencies and provides trading recommendations
    """
    
    def __init__(self):
        self.logger = logger
        
        # Algorithm parameters (can be tuned)
        self.min_confidence_threshold = 0.65  # Minimum confidence for trade recommendation
        self.api_weight_consensus = 0.4       # Weight for API consensus
        self.time_decay_factor = 0.1          # How much to discount older data
        self.volatility_threshold = 3.0       # Temperature volatility threshold (°F)
        self.market_efficiency_threshold = 0.15  # Price deviation threshold
        
    def load_historical_data(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load historical market and API performance data"""
        try:
            # Load API performance data
            api_data = pd.read_csv('api_deviance_detailed_results.csv')
            api_data['date'] = pd.to_datetime(api_data['date'])
            
            # Load market candlestick data
            market_data = pd.read_csv('data/candles/KXHIGHNY_candles_5m.csv')
            market_data['timestamp'] = pd.to_datetime(market_data['timestamp'])
            
            self.logger.info(f"Loaded {len(api_data)} API records and {len(market_data)} market records")
            return api_data, market_data
            
        except Exception as e:
            self.logger.error(f"Error loading historical data: {e}")
            return pd.DataFrame(), pd.DataFrame()
    
    def calculate_api_accuracy_weights(self, api_data: pd.DataFrame) -> Dict[str, float]:
        """Calculate accuracy weights for each weather API based on historical performance"""
        if api_data.empty:
            # Default weights if no historical data
            return {
                'nws': 0.25,
                'synoptic': 0.35,
                'asos': 0.40
            }
        
        # Calculate accuracy metrics for each API
        api_stats = {}
        
        for api in ['nws', 'synoptic', 'asos']:
            api_col = f'{api}_temp'
            if api_col in api_data.columns:
                # Filter out null values
                valid_data = api_data.dropna(subset=[api_col, 'kalshi_settlement'])
                
                if len(valid_data) > 0:
                    # Calculate mean absolute error
                    mae = np.mean(np.abs(valid_data[api_col] - valid_data['kalshi_settlement']))
                    
                    # Calculate accuracy (1 - normalized error)
                    max_error = np.std(valid_data['kalshi_settlement']) * 2  # 2 standard deviations
                    accuracy = max(0, 1 - (mae / max_error))
                    
                    api_stats[api] = {
                        'accuracy': accuracy,
                        'mae': mae,
                        'count': len(valid_data)
                    }
                    
                    self.logger.info(f"{api.upper()} API: Accuracy={accuracy:.3f}, MAE={mae:.2f}°F, N={len(valid_data)}")
        
        # Convert accuracies to weights (normalized)
        if api_stats:
            total_accuracy = sum(stats['accuracy'] for stats in api_stats.values())
            weights = {api: stats['accuracy'] / total_accuracy for api, stats in api_stats.items()}
        else:
            weights = {'nws': 0.33, 'synoptic': 0.33, 'asos': 0.34}
        
        self.logger.info(f"API weights: {weights}")
        return weights
    
    def analyze_market_patterns(self, market_data: pd.DataFrame) -> Dict:
        """Analyze historical market patterns for trading insights"""
        if market_data.empty:
            return {}
        
        patterns = {}
        
        # Group by date to analyze daily patterns
        market_data['date'] = market_data['timestamp'].dt.date
        daily_markets = market_data.groupby('date')
        
        # Analyze time-of-day patterns
        market_data['hour'] = market_data['timestamp'].dt.hour
        hourly_volatility = market_data.groupby('hour')['close'].std().to_dict()
        
        # Find optimal trading hours (highest volatility)
        optimal_hours = sorted(hourly_volatility.items(), key=lambda x: x[1], reverse=True)[:3]
        patterns['optimal_trading_hours'] = [hour for hour, vol in optimal_hours]
        
        # Analyze price movements relative to expiration
        patterns['pre_expiration_volatility'] = {}
        for date, group in daily_markets:
            if len(group) > 10:  # Need sufficient data points
                # Calculate volatility in final hours
                final_hours = group.tail(12)  # Last hour of trading (12 * 5min intervals)
                volatility = final_hours['close'].std()
                patterns['pre_expiration_volatility'][str(date)] = volatility
        
        # Calculate average market efficiency
        avg_efficiency = market_data.groupby('date').agg({
            'open': 'first',
            'close': 'last',
            'high': 'max',
            'low': 'min'
        })
        
        # Market efficiency = 1 - (price range / theoretical max range)
        avg_efficiency['range'] = avg_efficiency['high'] - avg_efficiency['low']
        avg_efficiency['efficiency'] = 1 - (avg_efficiency['range'] / 1.0)  # Max range is $1
        patterns['avg_market_efficiency'] = avg_efficiency['efficiency'].mean()
        
        self.logger.info(f"Market patterns: {json.dumps(patterns, indent=2, default=str)}")
        return patterns
    
    def generate_weather_consensus(self, apis_data: Dict[str, float], api_weights: Dict[str, float]) -> Dict:
        """Generate weighted consensus from weather APIs"""
        valid_apis = {api: temp for api, temp in apis_data.items() if temp is not None}
        
        if not valid_apis:
            return {'consensus_temp': None, 'confidence': 0.0, 'api_agreement': 0.0}
        
        # Calculate weighted consensus
        total_weight = sum(api_weights.get(api, 0) for api in valid_apis.keys())
        if total_weight == 0:
            return {'consensus_temp': None, 'confidence': 0.0, 'api_agreement': 0.0}
        
        consensus_temp = sum(
            temp * api_weights.get(api, 0) 
            for api, temp in valid_apis.items()
        ) / total_weight
        
        # Calculate API agreement (inverse of standard deviation)
        temps = list(valid_apis.values())
        if len(temps) > 1:
            api_agreement = max(0, 1 - (np.std(temps) / self.volatility_threshold))
        else:
            api_agreement = 1.0  # Perfect agreement with single API
        
        # Calculate confidence based on number of APIs and agreement
        confidence = (len(valid_apis) / 3.0) * api_agreement
        
        return {
            'consensus_temp': round(consensus_temp, 1),
            'confidence': confidence,
            'api_agreement': api_agreement,
            'api_count': len(valid_apis),
            'temp_range': max(temps) - min(temps) if len(temps) > 1 else 0
        }
    
    def analyze_market_efficiency(self, current_price: float, strike_temp: int, 
                                consensus_temp: float, confidence: float) -> Dict:
        """Analyze if current market price represents an inefficiency"""
        if consensus_temp is None:
            return {'inefficiency': 0.0, 'direction': 'hold', 'edge': 0.0}
        
        # Calculate theoretical probability based on consensus
        temp_diff = abs(consensus_temp - strike_temp)
        
        # Probability model: closer to strike = higher probability
        # Using normal distribution assumption with std dev = 3°F
        theoretical_prob = max(0.01, min(0.99, 
            np.exp(-(temp_diff ** 2) / (2 * self.volatility_threshold ** 2))
        ))
        
        # Adjust probability based on confidence
        adjusted_prob = theoretical_prob * confidence + 0.5 * (1 - confidence)
        
        # Calculate inefficiency
        price_inefficiency = abs(current_price - adjusted_prob)
        
        # Determine trading direction
        if current_price < adjusted_prob - self.market_efficiency_threshold:
            direction = 'buy'
            edge = adjusted_prob - current_price
        elif current_price > adjusted_prob + self.market_efficiency_threshold:
            direction = 'sell'
            edge = current_price - adjusted_prob
        else:
            direction = 'hold'
            edge = 0.0
        
        return {
            'inefficiency': price_inefficiency,
            'direction': direction,
            'edge': edge,
            'theoretical_prob': theoretical_prob,
            'adjusted_prob': adjusted_prob,
            'temp_diff': temp_diff
        }
    
    def generate_recommendation(self, market_ticker: str, strike_temp: int, 
                              current_price: float, apis_data: Dict[str, float],
                              time_to_expiration: timedelta = None) -> Dict:
        """Generate trading recommendation for a specific market"""
        
        # Load historical data for context
        api_data, market_data = self.load_historical_data()
        api_weights = self.calculate_api_accuracy_weights(api_data)
        market_patterns = self.analyze_market_patterns(market_data)
        
        # Generate weather consensus
        consensus = self.generate_weather_consensus(apis_data, api_weights)
        
        # Analyze market efficiency
        efficiency = self.analyze_market_efficiency(
            current_price, strike_temp, 
            consensus['consensus_temp'], consensus['confidence']
        )
        
        # Time decay adjustment
        time_factor = 1.0
        if time_to_expiration:
            hours_remaining = time_to_expiration.total_seconds() / 3600
            # Less confidence as expiration approaches (after 6 hours)
            if hours_remaining < 6:
                time_factor = max(0.5, hours_remaining / 6.0)
        
        # Final recommendation confidence
        final_confidence = (
            consensus['confidence'] * self.api_weight_consensus +
            efficiency['inefficiency'] * (1 - self.api_weight_consensus)
        ) * time_factor
        
        # Make recommendation
        recommendation = 'HOLD'
        if (final_confidence > self.min_confidence_threshold and 
            efficiency['edge'] > self.market_efficiency_threshold):
            recommendation = efficiency['direction'].upper()
        
        return {
            'ticker': market_ticker,
            'strike_temp': strike_temp,
            'current_price': current_price,
            'recommendation': recommendation,
            'confidence': final_confidence,
            'edge': efficiency['edge'],
            'consensus_temp': consensus['consensus_temp'],
            'api_agreement': consensus['api_agreement'],
            'temp_range': consensus['temp_range'],
            'theoretical_prob': efficiency['theoretical_prob'],
            'time_factor': time_factor,
            'reasoning': {
                'apis_used': list(apis_data.keys()),
                'temp_vs_strike': consensus['consensus_temp'] - strike_temp if consensus['consensus_temp'] else None,
                'price_inefficiency': efficiency['inefficiency'],
                'market_direction': efficiency['direction']
            }
        }
    
    def analyze_multiple_strikes(self, markets_data: List[Dict]) -> List[Dict]:
        """Analyze multiple strike prices for optimal trading opportunities"""
        recommendations = []
        
        for market in markets_data:
            rec = self.generate_recommendation(
                market['ticker'],
                market['strike_temp'], 
                market['current_price'],
                market['apis_data'],
                market.get('time_to_expiration')
            )
            recommendations.append(rec)
        
        # Sort by edge (profit potential)
        recommendations.sort(key=lambda x: x['edge'], reverse=True)
        
        return recommendations

def main():
    """Test the trading algorithm with sample data"""
    algo = KalshiTradingAlgorithm()
    
    # Sample market data for testing
    sample_markets = [
        {
            'ticker': 'KXHIGHNY-25AUG-80',
            'strike_temp': 80,
            'current_price': 0.45,
            'apis_data': {
                'nws': 82.1,
                'synoptic': 81.8,
                'asos': 82.3
            },
            'time_to_expiration': timedelta(hours=8)
        },
        {
            'ticker': 'KXHIGHNY-25AUG-85',
            'strike_temp': 85,
            'current_price': 0.15,
            'apis_data': {
                'nws': 82.1,
                'synoptic': 81.8,
                'asos': 82.3
            },
            'time_to_expiration': timedelta(hours=8)
        }
    ]
    
    recommendations = algo.analyze_multiple_strikes(sample_markets)
    
    print("\n🤖 KALSHI TRADING RECOMMENDATIONS 🤖")
    print("=" * 50)
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['ticker']}")
        print(f"   Strike: {rec['strike_temp']}°F | Price: ${rec['current_price']:.2f}")
        print(f"   📊 RECOMMENDATION: {rec['recommendation']} (Confidence: {rec['confidence']:.1%})")
        print(f"   🎯 Edge: {rec['edge']:.3f} | Consensus: {rec['consensus_temp']}°F")
        print(f"   📈 Theoretical Prob: {rec['theoretical_prob']:.1%}")
        
        if rec['recommendation'] != 'HOLD':
            print(f"   💡 Reasoning: APIs predict {rec['consensus_temp']}°F vs {rec['strike_temp']}°F strike")

if __name__ == "__main__":
    main()