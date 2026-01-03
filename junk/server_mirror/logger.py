import asyncio
import base64
import json
import time
import websockets
import requests
import csv
import os
from datetime import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\kalshi_prod_private_key.pem"
WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
API_URL = "https://api.elections.kalshi.com/trade-api/v2"
LOG_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\market_data.csv"

class OrderBookLogger:
    def __init__(self):
        self.books = {} # {ticker: {'yes': {price: qty}, 'no': {price: qty}}}
        self.init_csv()
        
    def init_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "market_ticker", "type", "price", "quantity", "side"])
            print(f"Created log file: {LOG_FILE}")

    def log_to_csv(self, ticker, price, side, msg_type="best_price"):
        """Log a specific price point to CSV."""
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            timestamp = datetime.now().isoformat()
            writer.writerow([timestamp, ticker, msg_type, price, "N/A", side])

    def update_book(self, ticker, side, price, qty):
        """Update the internal order book."""
        if ticker not in self.books:
            self.books[ticker] = {'yes': {}, 'no': {}}
            
        # Ensure price is integer cents
        price = int(price)
        
        if qty <= 0:
            if price in self.books[ticker][side]:
                del self.books[ticker][side][price]
        else:
            self.books[ticker][side][price] = qty

    def handle_snapshot(self, msg):
        """Process orderbook_snapshot message."""
        ticker = msg.get("market_ticker")
        if not ticker: return
        
        self.books[ticker] = {'yes': {}, 'no': {}}
        
        # Snapshot format: "yes": [[price, qty], ...]
        # Price might be string "0.99" or int 99? 
        # Based on logs, it seems to be string "0.9900".
        
        for p, q in msg.get("yes", []):
            try:
                # print(f"Snapshot YES price: {p}") # Debug
                price_cents = int(float(p))
                self.books[ticker]['yes'][price_cents] = q
            except: pass
            
        for p, q in msg.get("no", []):
            try:
                price_cents = int(float(p))
                self.books[ticker]['no'][price_cents] = q
            except: pass
            
        self.log_best_prices(ticker)

    def handle_delta(self, msg):
        """Process orderbook_delta message."""
        ticker = msg.get("market_ticker")
        if not ticker: return
        
        # Delta format: "price": 31, "delta": -1, "side": "no"
        # Price is integer cents.
        
        price = msg.get("price")
        delta = msg.get("delta")
        side = msg.get("side") # "yes" or "no"
        
        if ticker not in self.books:
             self.books[ticker] = {'yes': {}, 'no': {}}
        
        current_qty = self.books[ticker][side].get(price, 0)
        new_qty = current_qty + delta
        
        if new_qty <= 0:
            if price in self.books[ticker][side]:
                del self.books[ticker][side][price]
        else:
            self.books[ticker][side][price] = new_qty
            
        self.log_best_prices(ticker)

    def log_best_prices(self, ticker):
        """Calculate and log the best Bid/Ask."""
        book = self.books.get(ticker)
        if not book: return
        
        # Best YES Bid (Highest Price people are buying YES)
        yes_bids = book['yes'].keys()
        no_bids = book['no'].keys()
        
        # IGNORE EMPTY BOOKS
        if not yes_bids and not no_bids:
            return

        if yes_bids:
            best_yes_bid = max(yes_bids)
            # Log this. This is useful for "Selling YES".
            # Also implies "Buying NO" cost = 100 - best_yes_bid.
            
            # Visualizer wants "no_ask" (Cost to Buy NO).
            # Cost to Buy NO = 100 - Best YES Bid.
            no_ask = 100 - best_yes_bid
            self.log_to_csv(ticker, no_ask, "no_ask")
            
        # Best NO Bid (Highest Price people are buying NO)
        no_bids = book['no'].keys()
        if no_bids:
            best_no_bid = max(no_bids)
            # Log this. This is "Selling NO" price.
            # Visualizer might not use it, but good to have.
            # self.log_to_csv(ticker, best_no_bid, "no_bid")

def get_todays_highny_tickers():
    """Fetch ALL active KXHIGHNY market tickers for TODAY from the Production API."""
    tickers = set()
    try:
        print("Fetching active KXHIGHNY markets from Production API...")
        response = requests.get(f"{API_URL}/markets", params={"series_ticker": "KXHIGHNY", "status": "open"})
        if response.status_code == 200:
            data = response.json()
            markets = data.get("markets", [])
            if markets:
                today_str = datetime.now().strftime("%y%b%d").upper()
                for market in markets:
                    if today_str in market['ticker']:
                        tickers.add(market['ticker'])
                if tickers:
                    print(f"Found {len(tickers)} active markets for TODAY ({today_str}): {tickers}")
                else:
                    print(f"No markets found for TODAY ({today_str}).")
            else:
                print("No markets found for series KXHIGHNY.")
        else:
            print(f"Warning: Could not fetch markets. Status: {response.status_code}")
    except Exception as e:
        print(f"Error fetching markets: {e}")
    return tickers

def fetch_recent_candles(ticker, logger):
    """Fetch recent candlesticks to find last traded price."""
    try:
        end_ts = int(time.time())
        start_ts = end_ts - 86400 # Last 24 hours
        url = f"{API_URL}/series/KXHIGHNY/markets/{ticker}/candlesticks"
        params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": 60}
        
        print(f"Fetching candles for {ticker}...")
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            candles = data.get("candlesticks", [])
            if candles:
                for candle in reversed(candles):
                    price = candle.get("price", {})
                    close_price = price.get("close")
                    if close_price is not None and close_price > 0:
                        print(f"Found historical trade for {ticker}: {close_price}")
                        # Log as historical candle
                        with open(LOG_FILE, 'a', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerow([datetime.fromtimestamp(candle["end_period_ts"]).isoformat(), ticker, "candle", close_price, "N/A", "historical"])
                        return
            print(f"No non-zero historical data found for {ticker}")
    except Exception as e:
        print(f"Error fetching candles: {e}")

def sign_pss_text(private_key, text: str) -> str:
    message = text.encode('utf-8')
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def create_headers(private_key, method: str, path: str) -> dict:
    timestamp = str(int(time.time() * 1000))
    msg_string = timestamp + method + path.split('?')[0]
    signature = sign_pss_text(private_key, msg_string)
    return {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }

async def subscribe_to_tickers(websocket, tickers):
    if not tickers: return
    print(f"Subscribing to {len(tickers)} tickers: {tickers}")
    for ticker in tickers:
        subscribe_msg = {"id": 1, "cmd": "subscribe", "params": {"channels": ["orderbook_delta"], "market_ticker": ticker}}
        await websocket.send(json.dumps(subscribe_msg))
        await asyncio.sleep(0.1)

async def monitor_new_markets(websocket, subscribed_tickers):
    while True:
        await asyncio.sleep(60)
        print("Checking for new markets...")
        current_tickers = get_todays_highny_tickers()
        new_tickers = current_tickers - subscribed_tickers
        if new_tickers:
            print(f"Found {len(new_tickers)} NEW markets: {new_tickers}")
            await subscribe_to_tickers(websocket, new_tickers)
            subscribed_tickers.update(new_tickers)

async def orderbook_websocket():
    logger = OrderBookLogger()
    
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"Error: Private key file not found at {PRIVATE_KEY_PATH}")
        return

    ws_headers = create_headers(private_key, "GET", "/trade-api/ws/v2")
    
    print(f"Connecting to {WS_URL}...")
    async with websockets.connect(WS_URL, additional_headers=ws_headers) as websocket:
        print(f"Connected! Logging data to {LOG_FILE}")
        
        subscribed_tickers = get_todays_highny_tickers()
        await subscribe_to_tickers(websocket, subscribed_tickers)
        
        for ticker in subscribed_tickers:
            fetch_recent_candles(ticker, logger)
        
        monitor_task = asyncio.create_task(monitor_new_markets(websocket, subscribed_tickers))
        
        try:
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                msg = data.get("msg", {})
                
                if msg_type == "orderbook_snapshot":
                    logger.handle_snapshot(msg)
                elif msg_type == "orderbook_delta":
                    logger.handle_delta(msg)
                    
        except Exception as e:
            print(f"WebSocket connection error: {e}")
        finally:
            monitor_task.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(orderbook_websocket())
    except KeyboardInterrupt:
        print("Logging stopped by user.")
