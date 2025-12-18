import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import sys
import os
import time

# Add parent directory to path to import fetch modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.fetch_orderbook import get_markets_by_date
from utils.fetch_history import get_full_history
from utils.fetch_nws import get_nws_history

st.set_page_config(page_title="Strategy Backtester", layout="wide")

st.title("🧪 Strategy Backtester (DEBUG MODE)")
st.markdown("Simulate trading strategies over the past week with a **$100 starting budget**.")

# --- Sidebar Controls ---
st.sidebar.header("Configuration")
strategy = st.sidebar.selectbox(
    "Select Strategy",
    ["Safe (NWS Arbitrage)", "Risky (Momentum)", "Contrarian (Fade the Crowd)"]
)

days_back = st.sidebar.slider("Days to Backtest", 1, 7, 5)
initial_capital = st.sidebar.number_input("Initial Capital ($)", value=100)

run_btn = st.sidebar.button("Run Backtest", type="primary")

# --- Helper Functions ---

def get_trading_dates(days):
    """Get list of date strings (e.g., 'NOV20') for the last N days."""
    dates = []
    # Start from yesterday to avoid incomplete today data? 
    # Or include today? Let's go up to yesterday for safety in backtesting.
    start_date = datetime.now(timezone.utc) - timedelta(days=1)
    for i in range(days):
        d = start_date - timedelta(days=i)
        dates.append(d.strftime("%b%d").upper())
    return sorted(dates, key=lambda x: datetime.strptime(x, "%b%d").replace(year=2025))

def simulate_strategy(strategy_name, date_list, start_cap):
    portfolio_value = []
    trades = []
    cash = start_cap
    positions = [] # List of dicts: {ticker, type, entry_price, quantity, status}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_steps = len(date_list)
    
    for i, date_str in enumerate(date_list):
        status_text.text(f"Simulating {date_str}...")
        progress_bar.progress((i) / total_steps)
        
        # 1. Fetch Data
        markets = get_markets_by_date(date_str, status="open,closed,settled")
        if not markets:
            continue
            
        # NWS Data for this date
        # Parse date to get range
        month_str = date_str[:3]
        day_str = date_str[3:]
        month_num = datetime.strptime(month_str, "%b").month
        day_num = int(day_str)
        year = 2025 # Assumption
        
        start_dt = datetime(year, month_num, day_num, 14, 0, tzinfo=timezone.utc) # 9am ET
        end_dt = start_dt + timedelta(hours=24)
        
        nws_df = get_nws_history(start_dt, end_dt)
        if nws_df.empty:
            continue
            
        nws_df['timestamp'] = pd.to_datetime(nws_df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
        nws_df = nws_df.sort_values('timestamp')
        nws_df['cum_max'] = nws_df['temp_f'].expanding().max()
        
        # 2. Iterate through markets
        for market in markets:
            ticker = market['ticker']
            
            # Filter based on strategy needs
            if strategy_name == "Safe (NWS Arbitrage)":
                # Only look at "Below" markets or "Above" markets where event happened
                # Focus on B markets for "NO" bets (High >= Strike)
                if "-B" not in ticker: continue
                strike = float(ticker.split("-B")[1])
            elif strategy_name == "Risky (Momentum)":
                if "-T" not in ticker: continue
                strike = float(ticker.split("-T")[1])
            else:
                # Contrarian: Look at all
                if "-T" in ticker: strike = float(ticker.split("-T")[1])
                elif "-B" in ticker: strike = float(ticker.split("-B")[1])
                else: continue

            # Fetch Market History
            history = get_full_history(ticker)
            if not history: continue
            
            hist_df = pd.DataFrame(history)
            hist_df['time'] = pd.to_datetime(hist_df['end_period_ts'], unit='s', utc=True).dt.tz_convert('US/Eastern')
            hist_df = hist_df.sort_values('time')
            
            # Merge with tolerance to avoid stale prices
            # If no trade in the last 2 hours, assume illiquid/no quote.
            merged = pd.merge_asof(hist_df, nws_df, left_on='time', right_on='timestamp', direction='backward', tolerance=pd.Timedelta(hours=2))
            
            # 3. Simulate Minute-by-Minute (or Hour-by-Hour)
            for _, row in merged.iterrows():
                # If NWS data is missing (NaN due to tolerance), skip
                if pd.isna(row['timestamp']):
                    continue
                    
                current_time = row['time']
                current_max = row['cum_max']
                price_data = row['price']
                
                # Check if price is stale (compare candle time vs current simulation time? 
                # Actually, we are iterating over MARKET candles. So price is always "fresh" for that candle.
                # BUT, we are merging NWS to Market.
                # So for every Market Candle, we find the NWS data.
                # This ensures we only trade when there is VOLUME/Activity.
                # Wait, my previous logic was:
                # Iterate merged (which is Market History).
                # So we ONLY iterate when there was a trade/candle.
                # So why did we trade at 14:00 if there was no candle?
                
                # Ah! `get_full_history` returns hourly candles.
                # If there was no trade, Kalshi API might not return a candle?
                # Or it returns a candle with 0 volume?
                # Let's check the inspection output again.
                # 12:00, then 16:00.
                # There was NO candle at 14:00.
                # So how did `merged` have a row for 14:00?
                # It didn't!
                # If `merged` is based on `hist_df`, and `hist_df` has no 14:00 row, then `merged` has no 14:00 row.
                # So the loop shouldn't have run for 14:00.
                
                # Wait, did I use `nws_df` as the base?
                # No: `pd.merge_asof(hist_df, nws_df, ...)`
                # Left side is `hist_df`.
                # So we iterate over TRADES.
                
                # RE-READING CODE:
                # `merged = pd.merge_asof(hist_df, nws_df, left_on='time', right_on='timestamp', direction='backward')`
                # This keeps `hist_df` rows.
                
                # So where did the 14:00 trade come from?
                # Maybe `get_full_history` fills gaps?
                # Or maybe I am misreading the inspection output (maybe 14:00 IS there but I missed it?).
                # Inspection showed: 12:00, then 16:00.
                # If the backtester traded at 14:00, it implies `hist_df` HAD a row for 14:00.
                
                # Let's look at `fetch_history.py`.
                # It fetches `candlesticks`.
                # If Kalshi returns empty for that hour, no row.
                
                # HYPOTHESIS:
                # The `get_trading_dates` loop iterates dates.
                # For each date, we fetch history.
                # Maybe the "Nov 22" loop picked up a candle from Nov 21?
                # No.
                
                # Wait, look at the Trade Log again.
                # `NOV22 14:00`.
                # If `hist_df` had a row at 14:00, what was the price?
                # Inspection says NO ROW at 14:00.
                
                # Is it possible `nws_df` was the left side?
                # `merged = pd.merge_asof(hist_df, nws_df...)` -> Left is hist_df.
                
                # Wait, I might have swapped them in my head or code?
                # Code: `merged = pd.merge_asof(hist_df, nws_df, ...)`
                # Yes, Left is Hist.
                
                # So `hist_df` MUST have had a row.
                # Why did `inspect_nov22.py` NOT show it?
                # Maybe `inspect_nov22.py` used `get_full_history` which defaults to "now" and goes back?
                # And `backtester.py` uses... `get_full_history` too.
                
                # Maybe the ticker in backtester was different?
                # Log: `KXHIGHNY-25NOV22-B51.5`.
                # Inspect: `KXHIGHNY-25NOV22-B51.5`.
                
                # This is mysterious.
                # Unless... `hist_df` has 1-minute candles?
                # `fetch_history.py`: `period_interval: 60` (Hourly).
                
                # Let's add a check:
                # If Volume is 0 or low, skip.
                # And ensure we print the volume in the trade log for debugging.
                
                # Also, I will flip the merge.
                # We want to simulate "Checking the market every minute/hour".
                # So we should iterate over TIME (NWS data), and check the "Latest Market Price".
                # IF we iterate over Market Candles, we only trade when a trade happens.
                # But we want to trade when WE want (e.g. when NWS updates).
                # So `merged = pd.merge_asof(nws_df, hist_df, ...)` is actually more correct for a simulation?
                # YES!
                # If we iterate NWS (every minute), we look at the "last known price".
                # AND THIS IS WHERE THE BUG IS.
                # If I iterate NWS, and the last price was 2 hours ago (79c), I trade on it.
                # But in reality, if I tried to trade, the price wouldn't be 79c (it would be 100c or empty).
                
                # So, I WAS using `hist_df` as left in the code I wrote?
                # Let's check the file content of `pages/backtester.py`.

                
                if isinstance(price_data, dict):
                    yes_price = price_data.get('close')
                else:
                    yes_price = price_data
                    
                if yes_price is None: continue
                no_price = 100 - yes_price
                
                # --- STRATEGY LOGIC ---
                
                # SAFE: NWS Arbitrage
                if strategy_name == "Safe (NWS Arbitrage)":
                    # Target: B-markets (High < Strike). Bet NO (High >= Strike).
                    # Trigger: Current Max >= Strike (Event happened).
                    # Price: NO Price < 98 (Free money).
                    if "-B" in ticker:
                        if current_max >= strike:
                            # REALITY CHECK: If NO price is < 10 cents, the market is 90% sure we are wrong.
                            # This usually implies a data mismatch (e.g. NWS sensor error, lag).
                            # To avoid "fake" 2000% returns, we skip these "too good to be true" trades.
                            if no_price < 98 and no_price >= 10 and cash >= no_price/100:
                                # BUY NO
                                qty = int(cash // (no_price/100))
                                if qty > 0:
                                    cost = qty * (no_price/100)
                                    cash -= cost
                                    trades.append({
                                        "Date": date_str,
                                        "Time": current_time.strftime("%H:%M"),
                                        "Ticker": ticker,
                                        "Action": "BUY NO",
                                        "Price": no_price,
                                        "Qty": qty,
                                        "Reason": f"Max {current_max} >= Strike {strike}"
                                    })
                                    # Immediate Settlement (Simulated)
                                    # Since we know we won (Max >= Strike), we get $1.00 per share at end of day
                                    # For simplicity, let's credit it now? No, credit at end of loop.
                                    # Actually, let's just mark it as a position.
                                    positions.append({
                                        "ticker": ticker,
                                        "type": "NO",
                                        "qty": qty,
                                        "payout": 1.00 # Guaranteed win
                                    })
                                    # Break loop for this ticker (don't buy same thing 100 times)
                                    if "NOV22" in ticker:
                                        st.write(f"DEBUG: Buying {ticker} at {current_time}")
                                        st.write(f"Price: {no_price}, Max: {current_max}, Strike: {strike}")
                                        st.write(f"Row Timestamp: {row['timestamp']}, Row Time: {row['time']}")
                                    break
                
                # RISKY: Momentum
                # If temp jumped > 2 deg in last hour, bet YES on T-market just above current temp
                elif strategy_name == "Risky (Momentum)":
                    # Need previous temp... simplified:
                    # If Current Max is close to Strike (within 5 deg) and YES price is cheap (< 50)
                    # Bet YES hoping it hits.
                    if "-T" in ticker:
                        if (strike - current_max) < 5.0 and (strike - current_max) > 0:
                            # REALITY CHECK: Floor at 5 cents to avoid dead markets
                            if yes_price < 50 and yes_price >= 5 and cash >= yes_price/100:
                                # BUY YES
                                qty = int((cash * 0.5) // (yes_price/100)) # Bet 50% of cash
                                if qty > 0:
                                    cost = qty * (yes_price/100)
                                    cash -= cost
                                    trades.append({
                                        "Date": date_str,
                                        "Time": current_time.strftime("%H:%M"),
                                        "Ticker": ticker,
                                        "Action": "BUY YES",
                                        "Price": yes_price,
                                        "Qty": qty,
                                        "Reason": f"Momentum: Max {current_max} near Strike {strike}"
                                    })
                                    # Outcome? We need to know final max for this day.
                                    # We can check 'cum_max' of the LAST row of nws_df for this day.
                                    final_max = nws_df['cum_max'].iloc[-1]
                                    payout = 1.00 if final_max > strike else 0.00
                                    positions.append({
                                        "ticker": ticker,
                                        "type": "YES",
                                        "qty": qty,
                                        "payout": payout
                                    })
                                    break

                # CONTRARIAN: Fade the Crowd
                # If Prob > 90% but Strike is far away (> 4 deg), bet AGAINST.
                elif strategy_name == "Contrarian (Fade the Crowd)":
                    # If YES > 90, Buy NO.
                    if yes_price > 90:
                        # Check if safe to fade
                        # If T-market (High > Strike), and Current Max is < Strike - 4.
                        if "-T" in ticker and (strike - current_max) > 4:
                             if cash >= (100-yes_price)/100:
                                cost_per_share = (100-yes_price)/100
                                qty = int((cash * 0.2) // cost_per_share) # Bet 20%
                                if qty > 0:
                                    cost = qty * cost_per_share
                                    cash -= cost
                                    trades.append({
                                        "Date": date_str,
                                        "Time": current_time.strftime("%H:%M"),
                                        "Ticker": ticker,
                                        "Action": "BUY NO",
                                        "Price": 100-yes_price,
                                        "Qty": qty,
                                        "Reason": f"Fade: Price {yes_price} but Max {current_max} far from {strike}"
                                    })
                                    final_max = nws_df['cum_max'].iloc[-1]
                                    # Win if Final Max <= Strike (since we bought NO on T)
                                    payout = 1.00 if final_max <= strike else 0.00
                                    positions.append({
                                        "ticker": ticker,
                                        "type": "NO",
                                        "qty": qty,
                                        "payout": payout
                                    })
                                    break

        # End of Day Settlement
        day_pnl = 0
        for pos in positions:
            payout = pos['qty'] * pos['payout']
            cash += payout
            day_pnl += payout
        
        positions = [] # Clear positions
        portfolio_value.append({"Date": date_str, "Value": cash})
        
    progress_bar.progress(1.0)
    status_text.text("Simulation Complete.")
    return portfolio_value, trades

# --- Main Execution ---

if run_btn:
    date_list = get_trading_dates(days_back)
    
    with st.spinner(f"Running {strategy} on {len(date_list)} days..."):
        portfolio, trade_log = simulate_strategy(strategy, date_list, initial_capital)
    
    # Results
    st.markdown("### 📈 Performance")
    
    if portfolio:
        final_val = portfolio[-1]['Value']
        roi = ((final_val - initial_capital) / initial_capital) * 100
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Final Portfolio Value", f"${final_val:.2f}")
        col2.metric("Total Return (ROI)", f"{roi:.1f}%", delta=f"{final_val-initial_capital:.2f}")
        col3.metric("Trades Executed", len(trade_log))
        
        # Chart
        df_port = pd.DataFrame(portfolio)
        fig = px.line(df_port, x="Date", y="Value", title="Portfolio Growth", markers=True)
        fig.add_hline(y=initial_capital, line_dash="dash", line_color="gray", annotation_text="Start")
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.warning("No data or no trades executed.")

    # Trade Log
    st.markdown("### 📝 Trade Log")
    if trade_log:
        df_log = pd.DataFrame(trade_log)
        st.dataframe(df_log, use_container_width=True)
    else:
        st.info("No trades triggered based on strategy criteria.")
