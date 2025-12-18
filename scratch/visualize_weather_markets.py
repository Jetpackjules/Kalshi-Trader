import pandas as pd
import plotly.express as px
import re
from fetch_weather_markets import fetch_market_data

def parse_temperature(title):
    """
    Extracts temperature and type from the market title.
    Examples:
    "Will the high temp in NYC be >52° on Nov 19, 2025?" -> (52, "Above")
    "Will the high temp in NYC be <45° on Nov 19, 2025?" -> (45, "Below")
    "Will the high temp in NYC be 51-52° on Nov 19, 2025?" -> (51.5, "Range")
    """
    title = title.replace("**", "") # Remove bolding
    
    # Check for Range (e.g., 51-52)
    range_match = re.search(r'(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)°', title)
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        return (low + high) / 2, "Range"
        
    # Check for Greater Than (e.g., >52)
    gt_match = re.search(r'>(\d+(?:\.\d+)?)°', title)
    if gt_match:
        return float(gt_match.group(1)), "Above"
        
    # Check for Less Than (e.g., <45)
    lt_match = re.search(r'<(\d+(?:\.\d+)?)°', title)
    if lt_match:
        return float(lt_match.group(1)), "Below"
        
    return None, "Unknown"

def visualize_data():
    print("Fetching market data...")
    markets = fetch_market_data(days_back=5)
    
    if not markets:
        print("No data found to visualize.")
        return

    print(f"Processing {len(markets)} markets...")
    
    data = []
    for m in markets:
        temp, m_type = parse_temperature(m.get("title", ""))
        if temp is None:
            continue
            
        data.append({
            "Date": m.get("date_str"),
            "Temperature": temp,
            "Type": m_type,
            "Price": m.get("last_price", 0) / 100.0,
            "Volume": m.get("volume", 0),
            "Title": m.get("title"),
            "Ticker": m.get("ticker")
        })
        
    df = pd.DataFrame(data)
    
    # Create Scatter Plot
    fig = px.scatter(
        df, 
        x="Date", 
        y="Temperature", 
        color="Price",
        size="Volume",
        hover_data=["Title", "Price", "Volume"],
        symbol="Type",
        title="Kalshi NYC High Temp Markets (Last 5 Days)",
        color_continuous_scale="Viridis",
        size_max=40
    )
    
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Temperature (°F)",
        template="plotly_dark"
    )
    
    output_file = "weather_markets.html"
    fig.write_html(output_file)
    print(f"Visualization saved to {output_file}")

if __name__ == "__main__":
    visualize_data()
