"""
Kalshi Weather Orderbook Dashboard
Shows current market probabilities and temperature distributions
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from fetch_orderbook import (
    get_active_markets,
    get_orderbook,
    parse_market_date,
    parse_market_temp,
    get_best_price,
    calculate_implied_probability
)
# Updated with safe orderbook access

st.set_page_config(page_title="Kalshi Weather Markets", layout="wide")

st.title("🌡️ Kalshi NYC Weather Markets Dashboard")
st.markdown("Real-time orderbook data showing market-implied temperature probabilities")

# Fetch all active markets
with st.spinner("Fetching markets..."):
    markets = get_active_markets()

if not markets:
    st.error("No active markets found")
    st.stop()

# Parse market data
market_data = []
for market in markets:
    ticker = market["ticker"]
    date = parse_market_date(ticker)
    temp_info = parse_market_temp(ticker)
    
    if date and temp_info:
        temp_type, temp_value = temp_info
        
        # Fetch orderbook with defensive checks
        orderbook = get_orderbook(ticker)
        if not orderbook or not isinstance(orderbook, dict):
            orderbook = {"yes": [], "no": []}
            
        yes_price = get_best_price(orderbook, "yes")
        no_price = get_best_price(orderbook, "no")
        prob = calculate_implied_probability(yes_price, no_price)
        
        # Safe access for orderbook lengths
        yes_orders = len(orderbook.get("yes", []))
        no_orders = len(orderbook.get("no", []))
        
        market_data.append({
            "ticker": ticker,
            "date": date,
            "temp_type": temp_type,
            "temp": temp_value,
            "yes_price": yes_price,
            "no_price": no_price,
            "probability": prob,
            "yes_orders": yes_orders,
            "no_orders": no_orders
        })

df = pd.DataFrame(market_data)

# Date selector
dates = sorted(df["date"].unique())
selected_date = st.selectbox("Select Date", dates, index=0 if len(dates) > 0 else 0)

# Filter by selected date
df_filtered = df[df["date"] == selected_date].copy()

# Display metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Markets Found", len(df_filtered))
with col2:
    avg_prob = df_filtered["probability"].mean() if not df_filtered.empty else 0
    st.metric("Avg Probability", f"{avg_prob:.1%}")
with col3:
    total_orders = df_filtered["yes_orders"].sum() + df_filtered["no_orders"].sum()
    st.metric("Total Order Levels", int(total_orders))

# Temperature Distribution Chart
st.subheader(f"Temperature Probability Distribution - {selected_date}")

if not df_filtered.empty:
    # Sort by temperature
    df_plot = df_filtered.sort_values("temp").copy()
    
    # Create labels
    df_plot["label"] = df_plot.apply(
        lambda row: f"{'≥' if row['temp_type'] == 'T' else '<'}{row['temp']:.1f}°F",
        axis=1
    )
    
    # Create bar chart
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df_plot["label"],
        y=df_plot["probability"] * 100,
        text=df_plot["probability"].apply(lambda x: f"{x:.1%}" if x else "N/A"),
        textposition="outside",
        marker=dict(
            color=df_plot["probability"] * 100,
            colorscale="RdYlGn",
            showscale=True,
            colorbar=dict(title="Probability %")
        ),
        hovertemplate="<b>%{x}</b><br>Probability: %{y:.1f}%<extra></extra>"
    ))
    
    fig.update_layout(
        xaxis_title="Temperature Threshold",
        yaxis_title="Implied Probability (%)",
        yaxis=dict(range=[0, 100]),
        height=500,
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Market Details Table
    st.subheader("Market Details")
    
    display_df = df_plot[[
        "ticker", "label", "yes_price", "no_price", 
        "probability", "yes_orders", "no_orders"
    ]].copy()
    
    display_df.columns = [
        "Ticker", "Threshold", "YES Price (¢)", "NO Price (¢)",
        "Probability", "YES Levels", "NO Levels"
    ]
    
    # Format probability as percentage
    display_df["Probability"] = display_df["Probability"].apply(
        lambda x: f"{x:.1%}" if x else "N/A"
    )
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Detailed Orderbook View
    st.subheader("Orderbook Depth")
    
    selected_ticker = st.selectbox(
        "Select Market for Orderbook",
        df_plot["ticker"].tolist(),
        format_func=lambda t: f"{t} - {df_plot[df_plot['ticker']==t]['label'].iloc[0]}"
    )
    
    if selected_ticker:
        orderbook = get_orderbook(selected_ticker)
        if not orderbook or not isinstance(orderbook, dict):
            orderbook = {"yes": [], "no": []}
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**YES Orders**")
            if orderbook.get("yes"):
                yes_df = pd.DataFrame(orderbook["yes"], columns=["Price (¢)", "Quantity"])
                yes_df = yes_df.sort_values("Price (¢)", ascending=False)
                st.dataframe(yes_df, hide_index=True)
            else:
                st.info("No YES orders")
        
        with col2:
            st.markdown("**NO Orders**")
            if orderbook.get("no"):
                no_df = pd.DataFrame(orderbook["no"], columns=["Price (¢)", "Quantity"])
                no_df = no_df.sort_values("Price (¢)", ascending=False)
                st.dataframe(no_df, hide_index=True)
            else:
                st.info("No NO orders")

else:
    st.warning(f"No markets found for {selected_date}")

# Multi-Date Comparison
if len(dates) > 1:
    st.subheader("Multi-Date Comparison")
    
    selected_dates = st.multiselect(
        "Select dates to compare",
        dates,
        default=dates[:min(3, len(dates))]
    )
    
    if selected_dates:
        fig_comp = go.Figure()
        
        for date in selected_dates:
            df_date = df[df["date"] == date].sort_values("temp")
            df_date["label"] = df_date.apply(
                lambda row: f"{'≥' if row['temp_type'] == 'T' else '<'}{row['temp']:.1f}°F",
                axis=1
            )
            
            fig_comp.add_trace(go.Scatter(
                x=df_date["temp"],
                y=df_date["probability"] * 100,
                mode="lines+markers",
                name=date,
                hovertemplate=f"<b>{date}</b><br>Temp: %{{x:.1f}}°F<br>Prob: %{{y:.1f}}%<extra></extra>"
            ))
        
        fig_comp.update_layout(
            xaxis_title="Temperature (°F)",
            yaxis_title="Implied Probability (%)",
            yaxis=dict(range=[0, 100]),
            height=400,
            hovermode="x unified"
        )
        
        st.plotly_chart(fig_comp, use_container_width=True)
