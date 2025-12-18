import requests
import time
import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Optional

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
SERIES_TICKER = "KXHIGHNY"

# Path to local logs (relative to this file)
# this file is in dashboard/utils/
# logs are in live_trading_system/vm_logs/market_logs/
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../live_trading_system/vm_logs/market_logs"))

def get_history_from_logs(ticker: str, resample_rule: str = '1h') -> List[Dict]:
    """
    Attempts to fetch history from local CSV logs.
    resample_rule: Pandas resample rule (e.g., '1h', '1min'). If None, returns raw data points.
    """
    try:
        # Ticker format: KXHIGHNY-25DEC09-T32
        # Series format: KXHIGHNY-25DEC09
        parts = ticker.split('-')
        if len(parts) < 3:
            return []
            
        series_ticker = f"{parts[0]}-{parts[1]}"
        filename = f"market_data_{series_ticker}.csv"
        filepath = os.path.join(LOG_DIR, filename)
        
        if not os.path.exists(filepath):
            return []
            
        df = pd.read_csv(filepath)
        
        # Filter for specific ticker
        df = df[df['market_ticker'] == ticker].copy()
        if df.empty:
            return []
            
        # Convert timestamp
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df.set_index('timestamp', inplace=True)
        
        # We use 'implied_yes_ask' as the price
        price_col = 'implied_yes_ask'
        
        candles = []
        
        if resample_rule:
            # Resample
            ohlc = df[price_col].resample(resample_rule).ohlc()
            ohlc = ohlc.dropna()
            
            for ts, row in ohlc.iterrows():
                # Convert timestamp to unix seconds
                # For 1h, end_ts is start + 3600. For others, it depends.
                # Let's just use the timestamp as the "end" for simplicity or add the offset.
                # Actually, backtester uses end_period_ts to check if candle is "complete".
                # But for plotting, we just need a time.
                
                # Approximate duration in seconds
                duration = pd.to_timedelta(resample_rule).total_seconds()
                end_ts = int(ts.timestamp()) + int(duration)
                
                candles.append({
                    "end_period_ts": end_ts,
                    "price": {
                        "open": row['open'],
                        "high": row['high'],
                        "low": row['low'],
                        "close": row['close']
                    },
                    "volume": 0
                })
        else:
            # Raw Data
            # Treat each row as a "candle" with O=H=L=C = price
            for ts, row in df.iterrows():
                price = row[price_col]
                end_ts = int(ts.timestamp())
                candles.append({
                    "end_period_ts": end_ts,
                    "price": {
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price
                    },
                    "volume": 0
                })
            
        return candles

    except Exception as e:
        print(f"Error reading local logs for {ticker}: {e}")
        return []

    except Exception as e:
        print(f"Error reading local logs for {ticker}: {e}")
        return []

def get_market_history(ticker: str, start_ts: Optional[int] = None, end_ts: Optional[int] = None, days_back: int = 7) -> List[Dict]:
    """
    Fetch hourly candlestick history for a market.
    Prioritizes local logs, falls back to API.
    """
    # 1. Try Local Logs first
    local_candles = get_history_from_logs(ticker)
    if local_candles:
        # Filter by requested time range if provided
        filtered = []
        for c in local_candles:
            ts = c['end_period_ts']
            if start_ts and ts < start_ts:
                continue
            if end_ts and ts > end_ts:
                continue
            filtered.append(c)
        
        if filtered:
            return filtered

    # 2. Fallback to API
    now = int(time.time())
    if end_ts is None:
        end_ts = now
        
    if start_ts is None:
        start_ts = end_ts - (days_back * 86400)
    
    url = f"{BASE_URL}/series/{SERIES_TICKER}/markets/{ticker}/candlesticks"
    
    params = {
        "period_interval": 60, # Hourly
        "start_ts": int(start_ts),
        "end_ts": int(end_ts)
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("candlesticks", [])
    except Exception as e:
        print(f"Error fetching history for {ticker}: {e}")
        return []

def get_full_history(ticker: str) -> List[Dict]:
    """
    Fetch FULL history for a market by paginating backwards.
    """
    all_candles = []
    end_ts = int(time.time())
    chunk_size_hours = 4000 # Safe under 5000 limit
    chunk_size_sec = chunk_size_hours * 3600
    
    # We'll go back up to ~1 year (April is ~7 months ago)
    # Let's try 3 chunks of 4000 hours = 12000 hours = 500 days. Plenty.
    
    for i in range(3):
        start_ts = end_ts - chunk_size_sec
        
        candles = get_market_history(ticker, start_ts=start_ts, end_ts=end_ts)
        if not candles:
            break
            
        all_candles.extend(candles)
        
        # If we got fewer candles than the time range covers (significantly), 
        # we might have hit the start of the market.
        # But simplest is just to keep going back until no data.
        
        # Update end_ts for next chunk
        end_ts = start_ts
        
    # Deduplicate by timestamp just in case
    unique_candles = {c['end_period_ts']: c for c in all_candles}
    return sorted(unique_candles.values(), key=lambda x: x['end_period_ts'])

if __name__ == "__main__":
    # Test with a known ticker
    # Try to find an active one first, or use the one we know works
    ticker = "KXHIGHNY-25DEC09-T32" # Use a ticker we know we have logs for
    history = get_market_history(ticker, days_back=5)
    print(f"Fetched {len(history)} candles")
    if history:
        print("Sample candle:", history[-1])
