import requests
import re
import os
import pandas as pd
from typing import List, Dict, Optional, Tuple
from requests.exceptions import RequestException

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
# Path to local logs (relative to this file)
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../live_trading_system/vm_logs/market_logs"))

def get_active_markets(series_ticker: str = "KXHIGHNY", status: str = "open") -> List[Dict]:
    """
    Fetch all active markets for a given series.
    
    Args:
        series_ticker: Series ticker (default: KXHIGHNY for NYC high temp)
        status: Market status filter (default: open)
    
    Returns:
        List of market dictionaries
    """
    url = f"{BASE_URL}/markets?series_ticker={series_ticker}&status={status}&limit=200"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("markets", [])
    except RequestException as e:
        print(f"ERROR fetching markets: {e}")
        return []


def get_all_markets(series_ticker: str = "KXHIGHNY") -> List[Dict]:
    """
    Fetch ALL markets (active, closed, settled) for a given series.
    Useful for historical analysis.
    """
    # Fetch open, closed, and settled markets
    # We might need to make multiple calls or use a specific filter.
    # Let's try fetching without status to see if it returns everything, 
    # or explicitly asking for multiple statuses if the API supports it.
    # Based on typical Kalshi API, we iterate or fetch broadly.
    # Let's try a broad fetch.
    
    all_markets = []
    for status in ["open", "closed", "settled"]:
        url = f"{BASE_URL}/markets?series_ticker={series_ticker}&status={status}&limit=300" # Fetch plenty
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                markets = response.json().get("markets", [])
                all_markets.extend(markets)
        except Exception as e:
            print(f"Error fetching {status} markets: {e}")
            
    # Remove duplicates just in case
    seen = set()
    unique_markets = []
    for m in all_markets:
        if m['ticker'] not in seen:
            seen.add(m['ticker'])
            unique_markets.append(m)
            
    return unique_markets

def get_markets_from_logs(date_str: str, series_ticker: str = "KXHIGHNY") -> List[Dict]:
    """
    Discover markets from local CSV logs for a specific date.
    date_str: e.g. "NOV21" or "DEC09"
    """
    try:
        # Construct filename: market_data_KXHIGHNY-25DEC09.csv
        # We need to handle the year. Assuming 25 for now as per context.
        filename = f"market_data_{series_ticker}-25{date_str}.csv"
        filepath = os.path.join(LOG_DIR, filename)
        
        if not os.path.exists(filepath):
            return []
            
        # Read CSV to get unique tickers
        # We only need the 'market_ticker' column
        df = pd.read_csv(filepath, usecols=['market_ticker'])
        tickers = df['market_ticker'].unique()
        
        markets = []
        for ticker in tickers:
            # Parse ticker to get metadata
            # KXHIGHNY-25DEC09-T32
            # KXHIGHNY-25DEC09-B36.5
            
            # Extract Type and Strike
            match = re.search(r'-([TB])(\d+(?:\.\d+)?)', ticker)
            if match:
                m_type = match.group(1)
                strike = float(match.group(2))
                
                market = {
                    "ticker": ticker,
                    "series_ticker": series_ticker,
                    # Construct minimal metadata needed by backtester
                }
                
                if m_type == 'T':
                    market['strike_type'] = 'greater'
                    market['floor_strike'] = strike
                elif m_type == 'B':
                    market['strike_type'] = 'less'
                    market['cap_strike'] = strike
                
                markets.append(market)
                
        return markets

    except Exception as e:
        print(f"Error reading markets from logs for {date_str}: {e}")
        return []

def get_markets_by_date(date_str: str, series_ticker: str = "KXHIGHNY", status: str = "open,closed,settled") -> List[Dict]:
    """
    Fetch markets for a specific date string (e.g., "NOV21").
    Prioritizes local logs.
    """
    # 1. Try Local Logs
    local_markets = get_markets_from_logs(date_str, series_ticker)
    if local_markets:
        return local_markets

    # 2. Fallback to API
    from datetime import datetime, timezone, timedelta
    
    try:
        # Parse "NOV21"
        month_str = date_str[:3]
        day_str = date_str[3:]
        month_num = datetime.strptime(month_str, "%b").month
        day_num = int(day_str)
        year = 2025
        
        # Market Close: ~5am UTC on the NEXT day (Nov 22 for Nov 21 event)
        # Let's target the close time window.
        # Event Date: Nov 21
        # Expected Close: Nov 22 04:59 UTC
        
        # Window: Nov 22 00:00 UTC to Nov 22 12:00 UTC
        target_date = datetime(year, month_num, day_num)
        close_date = target_date + timedelta(days=1)
        
        min_ts = int(close_date.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc).timestamp())
        max_ts = int(close_date.replace(hour=12, minute=0, second=0, tzinfo=timezone.utc).timestamp())
        
        url = f"{BASE_URL}/markets"
        params = {
            "series_ticker": series_ticker,
            "min_close_ts": min_ts,
            "max_close_ts": max_ts,
            "limit": 100,
            "status": status # Use the passed status
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("markets", [])
        
    except Exception as e:
        print(f"Error fetching markets for {date_str}: {e}")
        return []


def get_orderbook(market_ticker: str) -> Dict:
    """
    Fetch orderbook data for a specific market.
    
    Args:
        market_ticker: Market ticker (e.g., "KXHIGHNY-25NOV21-T57")
    
    Returns:
        Dictionary with orderbook data: {"yes": [[price, qty], ...], "no": [[price, qty], ...]}
    """
    url = f"{BASE_URL}/markets/{market_ticker}/orderbook"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        orderbook = data.get("orderbook", {})
        
        # Handle None values from API (API returns null instead of empty array)
        yes_orders = orderbook.get("yes", [])
        no_orders = orderbook.get("no", [])
        
        return {
            "yes": yes_orders if yes_orders is not None else [],
            "no": no_orders if no_orders is not None else []
        }
    except RequestException as e:
        print(f"ERROR fetching orderbook for {market_ticker}: {e}")
        return {"yes": [], "no": []}


def parse_market_date(ticker: str) -> Optional[str]:
    """
    Extract date from market ticker.
    
    Args:
        ticker: Market ticker (e.g., "KXHIGHNY-25NOV18-T52")
    
    Returns:
        Date string (e.g., "NOV18") or None
    """
    # Pattern: KXHIGHNY-25NOV18-T52 -> NOV18
    match = re.search(r'-(\d{2}[A-Z]{3}\d{2})-', ticker)
    if match:
        date_str = match.group(1)  # "25NOV18"
        # Return month and day: "NOV18"
        return date_str[2:]
    return None


def parse_market_temp(ticker: str) -> Optional[Tuple[str, float]]:
    """
    Extract temperature threshold and type from market ticker.
    
    Args:
        ticker: Market ticker (e.g., "KXHIGHNY-25NOV18-T52" or "KXHIGHNY-25NOV18-B43.5")
    
    Returns:
        Tuple of (type, temperature) where type is "T" (>=) or "B" (<), or None
        Examples: ("T", 52.0), ("B", 43.5)
    """
    # Pattern: T52, T52.5, B43, B43.5, etc.
    match = re.search(r'-([TB])(\d+(?:\.\d+)?)', ticker)
    if match:
        temp_type = match.group(1)  # "T" or "B"
        temp_value = float(match.group(2))
        return (temp_type, temp_value)
    return None


def get_best_price(orderbook: Dict, side: str = "yes") -> Optional[int]:
    """
    Get best bid price from orderbook.
    
    Args:
        orderbook: Orderbook dict with "yes" and "no" lists
        side: "yes" or "no"
    
    Returns:
        Best price in cents, or None if no orders
    """
    orders = orderbook.get(side, [])
    if not orders:
        return None
    
    # Orders are [price, quantity] pairs
    # Best price is highest for buying
    prices = [order[0] for order in orders if len(order) >= 2]
    return max(prices) if prices else None


def calculate_implied_probability(yes_price: Optional[int], no_price: Optional[int]) -> Optional[float]:
    """
    Calculate implied probability from YES/NO prices.
    
    Args:
        yes_price: YES price in cents
        no_price: NO price in cents
    
    Returns:
        Probability as decimal (0.0-1.0), or None
    """
    if yes_price is not None:
        return yes_price / 100.0
    elif no_price is not None:
        return 1.0 - (no_price / 100.0)
    return None


if __name__ == "__main__":
    # Test the functions
    print("Fetching active markets...")
    markets = get_active_markets()
    print(f"Found {len(markets)} markets\n")
    
    if markets:
        # Test first market
        ticker = markets[0]["ticker"]
        print(f"Testing market: {ticker}")
        
        date = parse_market_date(ticker)
        temp = parse_market_temp(ticker)
        print(f"  Date: {date}")
        print(f"  Temperature: {temp}")
        
        orderbook = get_orderbook(ticker)
        yes_price = get_best_price(orderbook, "yes")
        no_price = get_best_price(orderbook, "no")
        prob = calculate_implied_probability(yes_price, no_price)
        
        print(f"  YES price: {yes_price}¢")
        print(f"  NO price: {no_price}¢")
        print(f"  Implied probability: {prob:.1%}" if prob else "  No probability")
