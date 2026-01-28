import asyncio
import json
import time
import websockets
import requests
import csv
import os
import base64
from datetime import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# ==========================================
# CONFIGURATION
# ==========================================
# TODO: Update these paths for your Google VM
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
# Assuming the key file is in the same directory as this script on the VM
PRIVATE_KEY_PATH = os.environ.get("KALSHI_PRIVATE_KEY", "kalshi_prod_private_key.pem")

WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
API_URL = "https://api.elections.kalshi.com/trade-api/v2"
LOG_DIR = os.environ.get("KALSHI_LOG_DIR", "market_logs") # Directory to store CSVs
# Hardcoded ladder logging settings (do not override via env)
LADDER_DEPTH = 10
LADDER_INTERVAL_S = 5.0
LADDER_TRIGGER_SPREAD = 0.0  # cents

# ==========================================
# AUTHENTICATION
# ==========================================
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

# ==========================================
# LOGGER LOGIC
# ==========================================
class GranularLogger:
    def __init__(self):
        self.books = {} # {ticker: {'yes': {price: qty}, 'no': {price: qty}}}
        self.last_logged_state = {} # {ticker: (best_yes_bid, best_yes_qty, best_no_bid, best_no_qty)}
        self.last_trade_price = {} # {ticker: last_trade_price_cents}
        self.last_ladder_log = {} # {ticker: last_log_ts}
        
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
            print(f"Created log directory: {LOG_DIR}")

    def get_log_file(self, ticker):
        """
        Generate filename based on the market's date code.
        Ticker format example: KXHIGHNY-23DEC04-T40
        We want to group by the date part: KXHIGHNY-23DEC04
        """
        try:
            # Extract the series and date part (e.g., KXHIGHNY-23DEC04)
            parts = ticker.split('-')
            if len(parts) >= 2:
                market_date_code = f"{parts[0]}-{parts[1]}"
            else:
                market_date_code = "UNKNOWN"
                
            filename = os.path.join(LOG_DIR, f"market_data_{market_date_code}.csv")
            return filename
        except Exception:
            return os.path.join(LOG_DIR, "market_data_misc.csv")

    def init_csv(self, ticker):
        """Ensure CSV exists with headers for this market group."""
        filename = self.get_log_file(ticker)
        if not os.path.exists(filename):
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", 
                    "market_ticker", 
                    "best_yes_bid", 
                    "best_yes_bid_qty",
                    "best_no_bid", 
                    "best_no_bid_qty",
                    "implied_no_ask", # 100 - best_yes_bid
                    "implied_no_ask_size", # qty at best yes bid
                    "implied_yes_ask", # 100 - best_no_bid
                    "implied_yes_ask_size", # qty at best no bid
                    "last_trade_price"
                ])
            print(f"Created new log file: {filename}")

    def get_ladder_file(self, ticker):
        try:
            parts = ticker.split('-')
            if len(parts) >= 2:
                market_date_code = f"{parts[0]}-{parts[1]}"
            else:
                market_date_code = "UNKNOWN"
            filename = os.path.join(LOG_DIR, f"orderbook_ladder_{market_date_code}.csv")
            return filename
        except Exception:
            return os.path.join(LOG_DIR, "orderbook_ladder_misc.csv")

    def init_ladder_csv(self, ticker):
        filename = self.get_ladder_file(ticker)
        if not os.path.exists(filename):
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "market_ticker",
                    "yes_bids",
                    "no_bids"
                ])
            print(f"Created ladder log file: {filename}")

    def log_ladder(self, ticker):
        if LADDER_DEPTH <= 0:
            return
        book = self.books.get(ticker)
        if not book:
            return
        yes_levels = sorted(book['yes'].items(), key=lambda x: x[0], reverse=True)[:LADDER_DEPTH]
        no_levels = sorted(book['no'].items(), key=lambda x: x[0], reverse=True)[:LADDER_DEPTH]
        filename = self.get_ladder_file(ticker)
        self.init_ladder_csv(ticker)
        try:
            with open(filename, 'a', newline='') as f:
                writer = csv.writer(f)
                timestamp = datetime.now().isoformat()
                writer.writerow([
                    timestamp,
                    ticker,
                    json.dumps(yes_levels),
                    json.dumps(no_levels)
                ])
        except Exception as e:
            print(f"Error writing ladder CSV: {e}")

    def maybe_log_ladder(self, ticker, spread_cents):
        if LADDER_DEPTH <= 0:
            return
        if LADDER_TRIGGER_SPREAD > 0 and spread_cents < LADDER_TRIGGER_SPREAD:
            return
        now_ts = time.time()
        last_ts = self.last_ladder_log.get(ticker, 0.0)
        if LADDER_INTERVAL_S > 0 and (now_ts - last_ts) < LADDER_INTERVAL_S:
            return
        self.log_ladder(ticker)
        self.last_ladder_log[ticker] = now_ts

    def log_state(self, ticker):
        """Log the current BBO if it has changed."""
        book = self.books.get(ticker)
        if not book: return

        # Calculate Best Yes Bid
        yes_bids = book['yes'].keys()
        best_yes_bid = max(yes_bids) if yes_bids else 0
        best_yes_bid_qty = book['yes'].get(best_yes_bid, 0) if best_yes_bid else 0
        
        # Calculate Best No Bid
        no_bids = book['no'].keys()
        best_no_bid = max(no_bids) if no_bids else 0
        best_no_bid_qty = book['no'].get(best_no_bid, 0) if best_no_bid else 0

        # Check if state changed
        current_state = (best_yes_bid, best_yes_bid_qty, best_no_bid, best_no_bid_qty)
        if self.last_logged_state.get(ticker) == current_state:
            return # No change in top of book

        # IGNORE EMPTY BOOKS (Market Closed/Settlement)
        if best_yes_bid == 0 and best_no_bid == 0:
            return

        # Update state
        self.last_logged_state[ticker] = current_state
        
        # Calculate Implied Asks (The price you pay to buy)
        # If I want to buy NO, I match with a YES seller. 
        # But in Kalshi's order book, "Selling YES" is the same as "Buying NO".
        # Wait, let's be precise:
        # The Order Book contains BIDS (people wanting to buy).
        # "Yes Bid" = Someone wants to BUY YES at X.
        # If I want to BUY NO, I can sell to the YES Bidder.
        # My "Buy NO" price = 100 - (Price I sell YES at).
        # So "Cost to Buy NO" = 100 - Best Yes Bid.
        
        implied_no_ask = 100 - best_yes_bid if best_yes_bid > 0 else 100
        implied_yes_ask = 100 - best_no_bid if best_no_bid > 0 else 100
        implied_no_ask_size = best_yes_bid_qty if best_yes_bid > 0 else 0
        implied_yes_ask_size = best_no_bid_qty if best_no_bid > 0 else 0

        spread_cents = implied_yes_ask - best_yes_bid if best_yes_bid > 0 else 0
        self.maybe_log_ladder(ticker, spread_cents)

        # Log to CSV
        filename = self.get_log_file(ticker)
        self.init_csv(ticker) # Ensure file exists
        
        try:
            with open(filename, 'a', newline='') as f:
                writer = csv.writer(f)
                timestamp = datetime.now().isoformat()
                last_trade = self.last_trade_price.get(ticker)
                writer.writerow([
                    timestamp,
                    ticker,
                    best_yes_bid,
                    best_yes_bid_qty,
                    best_no_bid,
                    best_no_bid_qty,
                    implied_no_ask,
                    implied_no_ask_size,
                    implied_yes_ask,
                    implied_yes_ask_size,
                    last_trade
                ])
            # print(f"Logged {ticker}: YesBid={best_yes_bid}, NoBid={best_no_bid}")
        except Exception as e:
            print(f"Error writing to CSV: {e}")

    def update_last_trade_prices(self, market_info: dict):
        """Cache last trade prices (in cents) from the markets endpoint."""
        for ticker, last_price in market_info.items():
            if last_price is None:
                continue
            try:
                self.last_trade_price[ticker] = int(last_price)
            except (TypeError, ValueError):
                continue

    def update_book(self, ticker, side, price, qty):
        """Update the internal order book."""
        if ticker not in self.books:
            self.books[ticker] = {'yes': {}, 'no': {}}
            
        price = int(price)
        
        if qty <= 0:
            if price in self.books[ticker][side]:
                del self.books[ticker][side][price]
        else:
            self.books[ticker][side][price] = qty
            
        self.log_state(ticker)

    def handle_snapshot(self, msg):
        ticker = msg.get("market_ticker")
        if not ticker: return
        
        self.books[ticker] = {'yes': {}, 'no': {}}
        
        for p, q in msg.get("yes", []):
            try:
                self.books[ticker]['yes'][int(float(p))] = q
            except: pass
            
        for p, q in msg.get("no", []):
            try:
                self.books[ticker]['no'][int(float(p))] = q
            except: pass
            
        self.log_state(ticker)

    def handle_delta(self, msg):
        ticker = msg.get("market_ticker")
        if not ticker: return
        
        price = msg.get("price")
        delta = msg.get("delta")
        side = msg.get("side")
        
        if ticker not in self.books:
             self.books[ticker] = {'yes': {}, 'no': {}}
        
        current_qty = self.books[ticker][side].get(price, 0)
        new_qty = current_qty + delta
        
        self.update_book(ticker, side, price, new_qty)

# ==========================================
# MAIN LOOP
# ==========================================
def fetch_active_markets():
    """Fetch ALL active KXHIGHNY market tickers and their last trade prices."""
    markets_out = {}
    try:
        print("Fetching active KXHIGHNY markets...")
        response = requests.get(f"{API_URL}/markets", params={"series_ticker": "KXHIGHNY", "status": "open"})
        if response.status_code == 200:
            data = response.json()
            markets = data.get("markets", [])
            for market in markets:
                ticker = market.get("ticker")
                if not ticker:
                    continue
                markets_out[ticker] = market.get("last_price")
            print(f"Found {len(markets_out)} active markets.")
        else:
            print(f"Error fetching markets: {response.status_code}")
    except Exception as e:
        print(f"Error fetching markets: {e}")
    return markets_out

async def subscribe_to_tickers(websocket, tickers):
    if not tickers: return
    print(f"Subscribing to {len(tickers)} tickers...")
    for ticker in tickers:
        msg = {"id": 1, "cmd": "subscribe", "params": {"channels": ["orderbook_delta"], "market_ticker": ticker}}
        await websocket.send(json.dumps(msg))
        await asyncio.sleep(0.05) # Rate limit protection

def update_manifest():
    """Write a JSON manifest of available log files for the dashboard."""
    try:
        files = [f for f in os.listdir(LOG_DIR) if f.endswith('.csv')]
        manifest = {
            "last_updated": datetime.now().isoformat(),
            "files": sorted(files)
        }
        # Write to temp file then rename for atomicity
        temp_path = os.path.join(LOG_DIR, "manifest.json.tmp")
        final_path = os.path.join(LOG_DIR, "manifest.json")
        
        with open(temp_path, "w") as f:
            json.dump(manifest, f)
        
        os.replace(temp_path, final_path)
    except Exception as e:
        print(f"Error updating manifest: {e}")

async def manifest_updater():
    """Periodically update the manifest file in the background."""
    print("Manifest updater started.")
    while True:
        try:
            update_manifest()
        except Exception as e:
            print(f"Manifest update error: {e}")
        await asyncio.sleep(10)

async def run_logger():
    logger = GranularLogger()
    
    # Load Private Key
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        print(f"CRITICAL: Private key not found at {PRIVATE_KEY_PATH}")
        print("Please ensure your .pem file is in the same directory.")
        return

    # Start Manifest Updater (only once)
    asyncio.create_task(manifest_updater())

    while True:
        try:
            # Connect
            ws_headers = create_headers(private_key, "GET", "/trade-api/ws/v2")
            print(f"Connecting to {WS_URL}...")
            
            async with websockets.connect(WS_URL, additional_headers=ws_headers) as websocket:
                print("Connected to WebSocket.")
                
                # Initial Subscription
                market_info = fetch_active_markets()
                subscribed_tickers = set(market_info)
                logger.update_last_trade_prices(market_info)
                await subscribe_to_tickers(websocket, subscribed_tickers)
                
                # Monitor Loop
                last_check_time = time.time()
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")
                        msg = data.get("msg", {})
                        
                        if msg_type == "orderbook_snapshot":
                            logger.handle_snapshot(msg)
                        elif msg_type == "orderbook_delta":
                            logger.handle_delta(msg)
                        
                        # Periodically check for new markets (every 5 mins)
                        if time.time() - last_check_time > 300:
                            print("Checking for new markets...")
                            market_info = fetch_active_markets()
                            current_tickers = set(market_info)
                            logger.update_last_trade_prices(market_info)
                            new_tickers = current_tickers - subscribed_tickers
                            if new_tickers:
                                print(f"New markets found: {new_tickers}")
                                await subscribe_to_tickers(websocket, new_tickers)
                                subscribed_tickers.update(new_tickers)
                            last_check_time = time.time()
                            
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        
        except Exception as e:
            print(f"Connection lost or error: {e}")
            print("Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(run_logger())
    except KeyboardInterrupt:
        print("Logger stopped.")
