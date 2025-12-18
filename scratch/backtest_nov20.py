import pandas as pd
from datetime import datetime, timezone, timedelta
from fetch_orderbook import get_markets_by_date
from fetch_history import get_full_history
from fetch_nws import get_nws_history
import pytz

def backtest_nov20():
    print("--- Backtesting Nov 20th Strategy ---")
    
    # 1. Fetch Markets for NOV20
    print("Fetching NOV20 markets...")
    markets = get_markets_by_date("NOV20")
    print(f"Found {len(markets)} markets.")
    
    if not markets:
        print("No markets found!")
        return

    # 2. Fetch NWS Data for Nov 20
    # Window: Nov 19 10am ET to Nov 20 11:59pm ET
    # UTC: Nov 19 15:00 to Nov 21 05:00
    start_dt = datetime(2025, 11, 19, 15, 0, tzinfo=timezone.utc)
    end_dt = datetime(2025, 11, 21, 5, 0, tzinfo=timezone.utc)
    
    print("Fetching NWS data...")
    nws_df = get_nws_history(start_dt, end_dt)
    if nws_df.empty:
        print("No NWS data found!")
        return
        
    # Pre-process NWS: Convert to ET and calculate cumulative max
    nws_df['timestamp'] = pd.to_datetime(nws_df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
    nws_df = nws_df.sort_values('timestamp')
    nws_df['cum_max'] = nws_df['temp_f'].expanding().max()
    
    # 3. Analyze Each Market
    opportunities = []
    
    for market in markets:
        ticker = market['ticker']
        # Parse Strike from ticker (e.g. KXHIGHNY-25NOV20-T52)
        # Assuming T (>=) markets for "NO" bets.
        # If it's B (<), a NO bet means >=. 
        
        # if "-T" not in ticker:
        #     continue
            
        if "-T" in ticker:
            strike = float(ticker.split("-T")[1])
        elif "-B" in ticker:
            strike = float(ticker.split("-B")[1])
        else:
            continue
        
        print(f"Analyzing {ticker} (Strike: {strike}°F)...")
        
        # Fetch Market History
        history = get_full_history(ticker)
        if not history:
            continue
            
        hist_df = pd.DataFrame(history)
        hist_df['time'] = pd.to_datetime(hist_df['end_period_ts'], unit='s', utc=True).dt.tz_convert('US/Eastern')
        hist_df = hist_df.sort_values('time')
        
        # Merge with NWS (As-of join)
        # For each market candle, what was the NWS Max *at that time*?
        merged = pd.merge_asof(hist_df, nws_df, left_on='time', right_on='timestamp', direction='backward')
        
        # 4. Find Entry Points
        # Criteria:
        # - NO Price <= 95 (YES Price >= 5) -> Potential 5% profit
        # - NO Price >= 90 (YES Price <= 10) -> Cap at 10% profit (safest range)
        # - Strike > NWS_Cum_Max + 2.0 (Safety Buffer)
        # - Time > 12:00 PM ET (Confidence increases as day passes)
        
        # Analyze B45.5 specifically
        if "B45.5" in ticker:
            print(f"Analyzing {ticker} (Strike: 45.5, Type: Below)...")
            
            no_prices = [100 - (row['price'].get('close') if isinstance(row['price'], dict) else row['price']) 
                         for _, row in merged.iterrows() 
                         if row['price'] is not None and (not isinstance(row['price'], dict) or row['price'].get('close') is not None)]
            
            if no_prices:
                print(f"Ticker {ticker}: Min NO Price={min(no_prices)}, Max NO Price={max(no_prices)}")
            
            for _, row in merged.iterrows():
                yes_price = row['price']
                if isinstance(yes_price, dict):
                    yes_price = yes_price.get('close')
                if yes_price is None: continue
                
                no_price = 100 - yes_price
                current_max = row['cum_max']
                current_time = row['time']
                
                # Debug every hour
                # print(f"{current_time.time()} | Max: {current_max} | NO Price: {no_price}")
                
                if 80 <= no_price <= 99:
                    opportunities.append({
                        "ticker": ticker,
                        "strike": 45.5,
                        "time": current_time,
                        "no_price": no_price,
                        "nws_max": current_max,
                        "cushion": current_max - 45.5, # Positive means we already won
                        "profit_potential": (100 - no_price) / no_price
                    })
    
    # 5. Summarize Best Opportunities
    if not opportunities:
        print("No opportunities found meeting criteria.")
        return
        
    opp_df = pd.DataFrame(opportunities)
    # Sort by Time (earliest entry) and Cushion (safest)
    best_opps = opp_df.sort_values(['time', 'cushion'], ascending=[True, False])
    
    print("\n=== TOP 5 SAFE 'NO' BET OPPORTUNITIES (Nov 20) ===")
    print(best_opps.head(10).to_string())
    
    # Save to CSV for review
    best_opps.to_csv("nov20_opportunities.csv", index=False)
    print("\nSaved full list to nov20_opportunities.csv")

if __name__ == "__main__":
    backtest_nov20()
