import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import sys
import os

# Add dashboard to path to import utils
sys.path.append(os.path.join(os.getcwd(), 'dashboard'))

from utils.fetch_history import get_full_history
from utils.fetch_nws import get_nws_history

def analyze_market_efficiency():
    print("Fetching historical data...")
    
    # Define date range (last 14 days for quick analysis)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=14)
    
    # 1. Fetch NWS Data
    print("Fetching NWS data...")
    nws_df = get_nws_history(start_date, end_date)
    if nws_df.empty:
        print("No NWS data found.")
        return

    nws_df['timestamp'] = pd.to_datetime(nws_df['timestamp'], utc=True)
    nws_df = nws_df.sort_values('timestamp')
    
    # Calculate daily max temps from NWS (approximate "High Temp" for the day)
    # Note: Kalshi markets are usually for a specific date.
    # We need to group NWS data by "Market Date".
    # Market Date usually aligns with Eastern Time day.
    
    nws_df['date_et'] = nws_df['timestamp'].dt.tz_convert('US/Eastern').dt.date
    daily_highs = nws_df.groupby('date_et')['temp_f'].max().reset_index()
    daily_highs.columns = ['date', 'actual_high']
    
    print(f"Found NWS data for {len(daily_highs)} days.")
    
    # 2. Fetch Market Data
    # We need to know which tickers to fetch.
    # We can infer tickers if we know the format: KXHIGHNY-YYMMDD-Txx
    # Or we can use get_markets_by_date if we iterate through dates.
    
    from utils.fetch_orderbook import get_markets_by_date
    
    analysis_data = []
    
    for _, row in daily_highs.iterrows():
        date_obj = row['date']
        actual_high = row['actual_high']
        
        # Format date for Kalshi: NOV21
        date_str = date_obj.strftime("%b%d").upper()
        print(f"Analyzing {date_str} (Actual High: {actual_high:.1f}F)...")
        
        markets = get_markets_by_date(date_str)
        if not markets:
            continue
            
        # For each market, get the closing price (or average price)
        # We want to see if the market correctly predicted the high.
        
        for market in markets:
            ticker = market['ticker']
            # Parse ticker to get threshold
            # KXHIGHNY-25NOV21-T50
            import re
            match = re.search(r'-T(\d+(?:\.\d+)?)', ticker)
            if not match:
                continue
                
            threshold = float(match.group(1))
            
            # Get history for this market
            history = get_full_history(ticker)
            if not history:
                continue
                
            # Analyze price evolution
            # We want to see the price at different times before close.
            # For simplicity, let's look at the price 1 hour before close vs result.
            
            # Sort history by time
            hist_df = pd.DataFrame(history)
            hist_df['ts'] = pd.to_datetime(hist_df['end_period_ts'], unit='s', utc=True)
            hist_df = hist_df.sort_values('ts')
            
            # Get strike type and values
            strike_type = market.get('strike_type')
            floor_strike = market.get('floor_strike')
            cap_strike = market.get('cap_strike')
            
            outcome = 0
            if strike_type == 'greater':
                # Ticker usually has floor_strike as the threshold
                if floor_strike is not None and actual_high > floor_strike:
                    outcome = 1
            elif strike_type == 'less':
                # Ticker usually has cap_strike as the threshold
                if cap_strike is not None and actual_high < cap_strike:
                    outcome = 1
            elif strike_type == 'between':
                if floor_strike is not None and cap_strike is not None:
                    if floor_strike <= actual_high < cap_strike:
                        outcome = 1
            else:
                # Fallback or unknown
                continue

            
            # Let's just store the last price for now to see if it converged
            last_trade = hist_df.iloc[-1]
            price_data = last_trade.get('price', {})
            if not isinstance(price_data, dict):
                continue
                
            last_price = price_data.get('close')
            
            if last_price is None:
                continue

            
            analysis_data.append({
                'date': date_str,
                'threshold': threshold,
                'actual_high': actual_high,
                'outcome': outcome,
                'last_price': last_price,
                'prediction_error': (last_price/100.0) - outcome
            })
            
    if not analysis_data:
        print("No analysis data generated.")
        return

    results_df = pd.DataFrame(analysis_data)
    print("\nAnalysis Results:")
    print(results_df.describe())
    
    # Save to CSV for inspection
    results_df.to_csv("strategy_analysis_results.csv", index=False)
    print("Saved results to strategy_analysis_results.csv")

if __name__ == "__main__":
    analyze_market_efficiency()
