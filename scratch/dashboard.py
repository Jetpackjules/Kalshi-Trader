import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
from datetime import timedelta
from fetch_weather_markets import fetch_market_data, fetch_market_history, get_kalshi_date_str

st.set_page_config(page_title="Kalshi Weather Dashboard", layout="wide")

st.title("Kalshi NYC Weather Market Dashboard")

# Sidebar: Date Selection
st.sidebar.header("Settings")
today = datetime.date.today()
date_options = [today - timedelta(days=i) for i in range(5)]
selected_date = st.sidebar.selectbox("Select Date", date_options, format_func=lambda x: x.strftime("%Y-%m-%d"))

# Fetch Markets for selected date
st.write(f"### Markets for {selected_date.strftime('%Y-%m-%d')}")
with st.spinner("Fetching markets..."):
    # We fetch 5 days back but filter for the selected date
    # A more efficient way would be to fetch just for that date, 
    # but our existing function fetches a range. We can reuse it or just fetch 1 day.
    # Let's just fetch 1 day by modifying how we call it or filtering.
    # Actually, fetch_market_data takes 'days_back'. 
    # Let's just fetch all 5 days and filter, it's fast enough for now.
    all_markets = fetch_market_data(days_back=5)
    
    # Filter for selected date
    date_str_kalshi = get_kalshi_date_str(selected_date)
    day_markets = [m for m in all_markets if m.get('date_str') == date_str_kalshi]

if not day_markets:
    st.warning("No markets found for this date.")
else:
    # Display Market Overview
    market_df = pd.DataFrame(day_markets)
    # Clean up for display
    display_df = market_df[['ticker', 'title', 'status', 'last_price', 'volume']].copy()
    display_df['last_price'] = display_df['last_price'] / 100.0
    st.dataframe(display_df, use_container_width=True)

    # Fetch History for all markets
    st.write("### Price History (Minute-by-Minute)")
    
    if st.button("Load Price History"):
        with st.spinner("Fetching historical data..."):
            all_history = []
            progress_bar = st.progress(0)
            
            for i, market in enumerate(day_markets):
                ticker = market['ticker']
                title = market['title']
                history = fetch_market_history(ticker, selected_date)
                
                for point in history:
                    point['Ticker'] = ticker
                    point['Title'] = title
                    all_history.append(point)
                
                progress_bar.progress((i + 1) / len(day_markets))
            
            if all_history:
                hist_df = pd.DataFrame(all_history)
                
                # Plot
                fig = px.line(
                    hist_df, 
                    x="time", 
                    y="price", 
                    color="Title", 
                    title=f"Price History for {selected_date}",
                    hover_data=["Ticker", "price"],
                    markers=True
                )
                fig.update_layout(yaxis_title="Price ($)", xaxis_title="Time (UTC)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No historical data available for these markets.")
