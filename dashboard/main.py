"""
Kalshi Weather Orderbook Dashboard
Shows current market probabilities, temperature distributions, and price history.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utils.fetch_orderbook import (
    get_active_markets,
    get_all_markets,
    get_markets_by_date,
    get_orderbook,
    parse_market_date,
    parse_market_temp,
    get_best_price,
    calculate_implied_probability
)
from utils.fetch_history import get_market_history, get_full_history
from utils.fetch_nws import get_nws_history
from datetime import timedelta, datetime, timezone
from plotly.subplots import make_subplots
st.markdown("Real-time orderbook data and historical price trends for NYC high temperatures.")

# Generate Date List (Static for speed)
from datetime import datetime, timedelta
st.sidebar.header("Settings")

# Generate dates: Last 30 days + Next 7 days
base_date = datetime(2025, 11, 21) # Hardcoded anchor for demo, or use today
# Actually, let's use a dynamic range around "today" (assuming 2025 context)
# If system time is 2025, use it. If not, anchor to Nov 2025.
now = datetime.now()
if now.year == 2025:
    anchor = now
else:
    anchor = datetime(2025, 11, 21)

date_list = []
for i in range(-30, 8):
    d = anchor + timedelta(days=i)
    date_list.append(d.strftime("%b%d").upper())

date_list = sorted(date_list, key=lambda x: datetime.strptime(x, "%b%d").replace(year=2025), reverse=True)

# Default to "NOV21" (or today) if available, otherwise index 0
default_date = anchor.strftime("%b%d").upper()
default_index = 0
if default_date in date_list:
    default_index = date_list.index(default_date)

selected_date = st.sidebar.selectbox("Select Event Date", date_list, index=default_index)

# Fetch markets for selected date
@st.cache_data(ttl=300)
def fetch_markets_for_date(date_str):
    return get_markets_by_date(date_str)

with st.spinner(f"Fetching markets for {selected_date}..."):
    markets = fetch_markets_for_date(selected_date)

if not markets:
    st.warning(f"No markets found for {selected_date}")
    # Optional: Allow fetching active markets as fallback?
    # st.stop() 
    # Let's not stop, just show empty state so user can pick another date.
else:
    # Process markets
    market_data = []
    for market in markets:
        ticker = market["ticker"]
        # ... rest of processing ...

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

# Filter by selected date (Already filtered by API, but good for safety)
if not df.empty:
    df_filtered = df[df["date"] == selected_date].copy()
else:
    df_filtered = pd.DataFrame()

# Add label column globally if data exists
if not df_filtered.empty:
    df_filtered["label"] = df_filtered.apply(
        lambda row: f"{'≥' if row['temp_type'] == 'T' else '<'}{row['temp']:.1f}°F",
        axis=1
    )

# Display metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Markets Found", len(df_filtered))
with col2:
    try:
        if not df_filtered.empty and "probability" in df_filtered.columns:
            avg_prob = df_filtered["probability"].mean()
        else:
            avg_prob = 0
        st.metric("Avg Probability", f"{avg_prob:.1%}")
    except Exception:
        st.metric("Avg Probability", "N/A")
with col3:
    try:
        if not df_filtered.empty and "yes_orders" in df_filtered.columns and "no_orders" in df_filtered.columns:
            total_orders = df_filtered["yes_orders"].sum() + df_filtered["no_orders"].sum()
        else:
            total_orders = 0
        st.metric("Total Order Levels", int(total_orders))
    except Exception:
        st.metric("Total Order Levels", "0")

st.markdown("---")

# --- MAIN SECTION: FULL HISTORY ---
st.header(f"📉 Market History: {selected_date}")
st.markdown("**NO Probability** (Implied from YES Price) over time for all markets.")

if not df_filtered.empty:
    # Auto-fetch if fewer than 5 markets to avoid waiting? 
    # No, let's keep it manual but prominent for now to be safe.
    if st.button("Load Full History Graph", type="primary", use_container_width=True):
        all_history = []
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        markets_to_fetch = df_filtered.to_dict('records')
        total_markets = len(markets_to_fetch)
        
        # Track min/max time for NWS fetch
        min_ts = float('inf')
        max_ts = 0
        
        for i, market in enumerate(markets_to_fetch):
            ticker = market['ticker']
            label = market['label']
            status_text.text(f"Fetching history for {label}...")
            
            # Fetch full history
            history_data = get_full_history(ticker)
            
            if history_data:
                market_hist_df = pd.DataFrame(history_data)
                # Convert to datetime UTC then to Eastern
                market_hist_df['date'] = pd.to_datetime(market_hist_df['end_period_ts'], unit='s', utc=True).dt.tz_convert('US/Eastern')
                
                # Update time range (keep as timestamps for min/max logic, but we need to be careful with NWS fetch)
                # Actually, let's use the converted dates for min/max to pass to NWS
                min_ts = min(min_ts, market_hist_df['end_period_ts'].min())
                max_ts = max(max_ts, market_hist_df['end_period_ts'].max())
                
                # NO Prob = 100 - YES Price
                market_hist_df['yes_price'] = market_hist_df['price'].apply(
                    lambda x: x.get('close') if isinstance(x, dict) else 0
                )
                market_hist_df['no_prob'] = 100 - market_hist_df['yes_price']
                market_hist_df['label'] = label
                market_hist_df['temp'] = market['temp']
                
                all_history.append(market_hist_df[['date', 'no_prob', 'label', 'yes_price', 'temp']])
            
            progress_bar.progress((i + 1) / total_markets)
        
        status_text.empty()
        progress_bar.empty()
        
        if all_history:
            combined_df = pd.concat(all_history)
            
            # Fetch NWS Data
            status_text.text("Fetching NWS Temperature Data...")
            nws_df = pd.DataFrame()
            if min_ts != float('inf'):
                # Convert min/max TS to UTC datetime for NWS fetch
                start_dt = datetime.fromtimestamp(min_ts, tz=timezone.utc)
                end_dt = datetime.fromtimestamp(max_ts, tz=timezone.utc)
                nws_df = get_nws_history(start_dt, end_dt)
                
                if not nws_df.empty:
                    # Convert NWS to Eastern
                    nws_df['timestamp'] = pd.to_datetime(nws_df['timestamp'], utc=True).dt.tz_convert('US/Eastern')
            status_text.empty()
            
            # --- Calculate Market Estimated Temp ---
            # Pivot to get matrix: Index=Date, Columns=Temp, Values=Yes_Price (Prob)
            try:
                pivot_df = combined_df.pivot_table(index='date', columns='temp', values='yes_price', aggfunc='mean')
                
                # Sort columns (temperatures)
                pivot_df = pivot_df.reindex(sorted(pivot_df.columns), axis=1)
                
                estimated_temps = []
                for date, row in pivot_df.iterrows():
                    # row is Series of Yes Prices (0-100) for each temp threshold
                    # P(T > X) = Price / 100
                    
                    temps = row.index.tolist()
                    prices = row.values.tolist()
                    
                    expected_val = 0
                    current_prob = 1.0 # Assume P(> min-epsilon) = 1
                    
                    # We calculate contribution of each bin [T_i, T_i+1]
                    # Prob(in bin) = P(> T_i) - P(> T_i+1)
                    # But our prices are P(> T_i). 
                    # Actually, Kalshi "High Temp" markets are usually "High >= X".
                    # So Price at T50 is P(Max >= 50).
                    
                    # Let's iterate through sorted thresholds
                    # T_0=48, T_1=49, ...
                    # P(Max >= 48) = 0.99
                    # P(Max >= 49) = 0.90
                    # Prob(48 <= Max < 49) = 0.99 - 0.90 = 0.09
                    # Value ~ 48.5
                    
                    # Handle the "tail" below the first threshold
                    first_thresh = temps[0]
                    first_prob = prices[0] / 100.0
                    # Bin (-inf, T_0): Prob = 1 - P(>= T_0). Value ~ T_0 - 0.5
                    expected_val += (1.0 - first_prob) * (first_thresh - 0.5)
                    
                    for i in range(len(temps) - 1):
                        t_curr = temps[i]
                        t_next = temps[i+1]
                        p_curr = prices[i] / 100.0
                        p_next = prices[i+1] / 100.0
                        
                        # Prob in bin [t_curr, t_next)
                        bin_prob = max(0, p_curr - p_next) # Ensure non-negative
                        bin_mid = (t_curr + t_next) / 2.0
                        
                        expected_val += bin_prob * bin_mid
                        
                    # Handle the "tail" above the last threshold
                    last_thresh = temps[-1]
                    last_prob = prices[-1] / 100.0
                    # Bin [T_last, inf): Prob = P(>= T_last). Value ~ T_last + 0.5
                    expected_val += last_prob * (last_thresh + 0.5)
                    
                    estimated_temps.append({'date': date, 'est_temp': expected_val})
                    
                est_temp_df = pd.DataFrame(estimated_temps)
            except Exception as e:
                print(f"Error calculating estimated temp: {e}")
                est_temp_df = pd.DataFrame()

            # --- Calculate NWS Cumulative Max ---
            if not nws_df.empty:
                nws_df = nws_df.sort_values('timestamp')
                nws_df['cum_max'] = nws_df['temp_f'].expanding().max()

            # Create Subplots (3 Rows)
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.05,
                row_heights=[0.5, 0.25, 0.25],
                subplot_titles=(
                    f"NO Probability History - {selected_date}", 
                    "NWS Temperature (KNYC)",
                    "Max Temp Analysis: Market Prediction vs. Reality"
                )
            )
            
            # Row 1: Market Lines
            colors = px.colors.qualitative.Plotly
            labels = combined_df['label'].unique()
            for i, label in enumerate(labels):
                subset = combined_df[combined_df['label'] == label]
                fig.add_trace(
                    go.Scatter(
                        x=subset['date'], 
                        y=subset['no_prob'],
                        name=label,
                        mode='lines',
                        line=dict(color=colors[i % len(colors)]),
                        legendgroup="markets"
                    ),
                    row=1, col=1
                )
                
            # Row 2: NWS Temp
            if not nws_df.empty:
                fig.add_trace(
                    go.Scatter(
                        x=nws_df['timestamp'],
                        y=nws_df['temp_f'],
                        name="NWS Temp",
                        line=dict(color='#00CC96', width=2), # Teal for visibility in Dark Mode
                        hovertemplate="%{y:.1f}°F<extra></extra>",
                        legendgroup="nws"
                    ),
                    row=2, col=1
                )
                
            # Row 3: Max Temp Analysis
            # 1. NWS Cumulative Max
            if not nws_df.empty:
                fig.add_trace(
                    go.Scatter(
                        x=nws_df['timestamp'],
                        y=nws_df['cum_max'],
                        name="NWS Max (Cumulative)",
                        line=dict(color='#EF553B', width=2), # Bright Red
                        hovertemplate="Real Max: %{y:.1f}°F<extra></extra>",
                        legendgroup="analysis"
                    ),
                    row=3, col=1
                )
                
            # 2. Market Estimated Max
            if not est_temp_df.empty:
                fig.add_trace(
                    go.Scatter(
                        x=est_temp_df['date'],
                        y=est_temp_df['est_temp'],
                        name="Market Est. Max",
                        line=dict(color='#AB63FA', width=2, dash='dot'), # Bright Purple
                        hovertemplate="Est Max: %{y:.1f}°F<extra></extra>",
                        legendgroup="analysis"
                    ),
                    row=3, col=1
                )
            
            # Market Hours Annotations (ET)
            try:
                # selected_date is e.g. "NOV21". We need year. 
                # Assuming current year or inferring from data. 
                # Actually, let's use the max date in the data as the anchor.
                if not combined_df.empty:
                    max_date = combined_df['date'].max()
                    event_year = max_date.year
                    
                    # Parse selected_date "NOV21" -> Month/Day
                    # This is tricky if we don't have the year in the string.
                    # But we have the data! 
                    # Let's just use the Open/Close relative to the data we have.
                    # The market closes at 11:59 PM ET on the event date.
                    # The event date is the date of the data points (mostly).
                    
                    # Better: Construct Open/Close based on the "Event Date" derived from the ticker.
                    # We know the event date is "NOV21".
                    # Let's assume the year is the same as the data.
                    
                    # Construct Event Date Object (Midnight ET)
                    # We can use the max timestamp in the data, which should be near the close.
                    # Or just parse the string "NOV21" + Year.
                    
                    from datetime import datetime
                    import pytz
                    et_tz = pytz.timezone('US/Eastern')
                    
                    # Parse "NOV21"
                    month_str = selected_date[:3]
                    day_str = selected_date[3:]
                    month_num = datetime.strptime(month_str, "%b").month
                    
                    # Use year from data
                    year = max_date.year
                    
                    # Event Date: Year-Month-Day
                    event_dt = datetime(year, month_num, int(day_str))
                    event_dt = et_tz.localize(event_dt)
                    
                    # Open: 10:00 AM ET Day Before
                    open_time = (event_dt - timedelta(days=1)).replace(hour=10, minute=0)
                    
                    # Close: 11:59 PM ET Day Of
                    close_time = event_dt.replace(hour=23, minute=59)
                    
                    # Current Time (ET)
                    now_et = datetime.now(et_tz)

                    # Add to all subplots
                    for r in [1, 2, 3]:
                        # Open/Close Range
                        fig.add_vrect(
                            x0=open_time, x1=close_time,
                            fillcolor="green", opacity=0.05,
                            layer="below", line_width=0,
                            row=r, col=1
                        )
                        fig.add_vline(x=open_time, line_dash="dash", line_color="green", row=r, col=1)
                        fig.add_vline(x=close_time, line_dash="dash", line_color="red", row=r, col=1)
                        
                        # Current Time Line (if within range)
                        if open_time <= now_et <= close_time + timedelta(hours=1): # Show if recent
                            fig.add_vline(
                                x=now_et, 
                                line_dash="dot", 
                                line_color="black", 
                                line_width=1,
                                annotation_text="Now",
                                annotation_position="bottom right",
                                row=r, col=1
                            )
                
            except Exception as e:
                print(f"Error adding annotations: {e}")

            fig.update_layout(
                height=1000,
                hovermode="x unified",
                legend=dict(orientation="h", y=1.01, x=1, xanchor="right"),
                title_text=f"Market History ({selected_date}) - All Times US/Eastern"
            )
            
            fig.update_yaxes(title_text="NO Prob (%)", range=[0, 100], row=1, col=1)
            fig.update_yaxes(title_text="Temp (°F)", row=2, col=1)
            fig.update_yaxes(title_text="Max Temp (°F)", row=3, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("No historical data found for any markets on this date.")
    else:
        st.info("👆 Click the button above to load the full history graph.")
else:
    st.warning("No markets available.")

st.markdown("---")

# --- SECONDARY SECTION: CURRENT STATE ---
with st.expander("📊 Current Market Distribution & Orderbooks", expanded=False):
    tab1, tab2 = st.tabs(["Probability Distribution", "Orderbook Depth"])
    
    with tab1:
        st.subheader(f"Snapshot: {selected_date}")
        if not df_filtered.empty:
            df_plot = df_filtered.sort_values("temp").copy()
            
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
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Table
            display_df = df_plot[[
                "ticker", "label", "yes_price", "no_price", 
                "probability", "yes_orders", "no_orders"
            ]].copy()
            display_df.columns = ["Ticker", "Threshold", "YES ¢", "NO ¢", "Prob", "YES Lvl", "NO Lvl"]
            display_df["Prob"] = display_df["Prob"].apply(lambda x: f"{x:.1%}" if x else "N/A")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.warning(f"No markets found for {selected_date}")

    with tab2:
        if not df_filtered.empty:
            selected_ticker = st.selectbox(
                "Select Market",
                df_filtered["ticker"].tolist(),
                format_func=lambda t: f"{t} - {df_filtered[df_filtered['ticker']==t]['label'].iloc[0]}"
            )
            
            if selected_ticker:
                orderbook = get_orderbook(selected_ticker)
                if not orderbook or not isinstance(orderbook, dict):
                    orderbook = {"yes": [], "no": []}
                
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**YES Orders**")
                    if orderbook.get("yes"):
                        st.dataframe(pd.DataFrame(orderbook["yes"], columns=["Price", "Qty"]).sort_values("Price", ascending=False), hide_index=True)
                    else:
                        st.info("Empty")
                with c2:
                    st.markdown("**NO Orders**")
                    if orderbook.get("no"):
                        st.dataframe(pd.DataFrame(orderbook["no"], columns=["Price", "Qty"]).sort_values("Price", ascending=False), hide_index=True)
                    else:
                        st.info("Empty")
        else:
            st.warning("No markets available.")

# Multi-Date Comparison (Below tabs)
if len(date_list) > 1:
    st.markdown("---")
    st.subheader("Multi-Date Comparison")
    
    selected_dates = st.multiselect(
        "Select dates to compare",
        date_list,
        default=date_list[:min(3, len(date_list))]
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
