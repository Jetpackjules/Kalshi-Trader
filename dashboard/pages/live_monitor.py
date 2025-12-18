import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import pytz
import sys
import os
import time

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.fetch_orderbook import get_markets_by_date
from utils.fetch_nws import get_nws_history
from utils.fetch_history import get_market_history

st.set_page_config(page_title="Live Monitor", layout="wide")

st.title("📡 Live Market Monitor (PST)")
st.markdown("Real-time view of **Today's Markets** and **NWS Weather Data**.")

# Auto-refresh
if st.button("Refresh Data"):
    st.rerun()

# Timezone Setup
utc = timezone.utc
pst = pytz.timezone('US/Pacific')
est = pytz.timezone('US/Eastern')

# Get Today's Date (in ET, as Kalshi uses ET dates usually, or just "NOV23")
now_pst = datetime.now(pst)
date_str = now_pst.strftime("%b%d").upper() # e.g. "NOV23"

st.write(f"**Current Time (PST):** {now_pst.strftime('%Y-%m-%d %H:%M:%S')}")
st.write(f"**Target Date:** {date_str}")

# 1. Fetch NWS Data (Last 24 hours to capture today)
st.subheader("🌡️ NWS Weather Data (Central Park)")
start_dt = datetime.now(timezone.utc) - timedelta(hours=24)
end_dt = datetime.now(timezone.utc)
nws_df = get_nws_history(start_dt, end_dt)

if not nws_df.empty:
    # Convert to PST
    nws_df['timestamp'] = pd.to_datetime(nws_df['timestamp'], utc=True).dt.tz_convert(pst)
    nws_df = nws_df.sort_values('timestamp', ascending=False)
    
    # Calculate Max for Today (Since Midnight PST)
    today_pst = now_pst.replace(hour=0, minute=0, second=0, microsecond=0)
    today_df = nws_df[nws_df['timestamp'] >= today_pst]
    
    current_temp = nws_df.iloc[0]['temp_f']
    max_temp_today = today_df['temp_f'].max() if not today_df.empty else "N/A"
    
    col1, col2 = st.columns(2)
    col1.metric("Current Temp", f"{current_temp}°F")
    col2.metric("Max Temp Today (Since Midnight PST)", f"{max_temp_today}°F")
    
    st.dataframe(nws_df[['timestamp', 'temp_f']].head(10).style.format({"temp_f": "{:.1f}"}))
else:
    st.error("No NWS Data Found.")

# 2. Fetch Markets
st.subheader(f"📊 Kalshi Markets ({date_str})")
markets = get_markets_by_date(date_str, status="open,closed,settled")

if markets:
    market_data = []
    for m in markets:
        ticker = m['ticker']
        # Fetch latest quote
        # We can use get_market_history(days_back=1) and take the last one?
        # Or just use the market data if it has 'last_price'?
        # get_markets_by_date returns basic info.
        # Let's fetch history for the last hour to get the LATEST price.
        
        hist = get_market_history(ticker, days_back=1)
        last_price = "N/A"
        last_trade_time = "N/A"
        
        if hist:
            last_candle = hist[-1]
            last_price = last_candle.get('close')
            ts = last_candle.get('end_period_ts')
            last_trade_time = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(pst).strftime('%H:%M PST')
            
        market_data.append({
            "Ticker": ticker,
            "Status": m.get('status'),
            "Last Price": last_price,
            "Last Trade": last_trade_time
        })
        
    df_markets = pd.DataFrame(market_data)
    st.dataframe(df_markets)
else:
    st.info(f"No markets found for {date_str}.")

# Auto-refresh every 60s
time.sleep(1)
st.empty() # Placeholder
# st.rerun() # Uncomment for auto-refresh loop, but button is safer for now.
