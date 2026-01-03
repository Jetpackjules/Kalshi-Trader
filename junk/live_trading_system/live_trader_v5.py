import asyncio
import base64
import json
import time
import requests
import csv
import os
import uuid
import glob
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# --- Configuration ---
LOG_DIR = "market_logs"
TRADES_LOG_FILE = "trades.csv"

# API Config
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = "kalshi_prod_private_key.pem"
API_URL = "https://api.elections.kalshi.com"

# --- API Helpers ---
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

def get_balance(private_key):
    """Fetch current available balance and portfolio value in dollars."""
    path = "/trade-api/v2/portfolio/balance"
    method = "GET"
    headers = create_headers(private_key, method, path)
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            balance = data.get("balance", 0) / 100.0
            portfolio_value = data.get("portfolio_value", 0) / 100.0
            return balance, portfolio_value
        return 0.0, 0.0
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return 0.0, 0.0

def get_positions(private_key):
    """Fetch current portfolio positions."""
    path = "/trade-api/v2/portfolio/positions"
    method = "GET"
    headers = create_headers(private_key, method, path)
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            return response.json().get("market_positions", [])
        return []
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []

def place_real_order(ticker, count, price, side):
    """Executes a REAL order on Kalshi with Robust Error Handling."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except Exception as e:
        print(f"CRITICAL: Failed to load private key: {e}")
        return False

    path = "/trade-api/v2/portfolio/orders"
    method = "POST"
    order_id = str(uuid.uuid4())
    
    # AGGRESSIVE LIMIT: Ensure fill by paying 1 tick over Ask
    # If Buying YES at 50, Limit = 51.
    # If Buying NO at 50, Limit = 51.
    aggressive_price = min(99, price + 1)
    
    payload = {
        "action": "buy",
        "count": count,
        "side": side,
        "ticker": ticker,
        "type": "limit",
        "yes_price" if side == 'yes' else "no_price": aggressive_price,
        "client_order_id": order_id
    }
    
    headers = create_headers(private_key, method, path)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 SENDING ORDER: {ticker} {side.upper()} {count} @ {aggressive_price} (Target: {price})")
    
    try:
        response = requests.post(f"{API_URL}{path}", headers=headers, json=payload)
        
        if response.status_code == 201:
            data = response.json()
            order_id_resp = data.get("order", {}).get("order_id", "Unknown")
            print(f"✅ SUCCESS: Order Placed! ID: {order_id_resp}")
            return True
        else:
            # LOG THE ERROR!
            print(f"❌ FAILED: Status {response.status_code}")
            print(f"❌ RESPONSE: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION during API Call: {e}")
        return False

# --- Strategy ---
class SafeBaselineStrategy:
    def __init__(self, risk_pct=0.50):
        self.name = "Safe Baseline (Wait 120m | Risk 50%)"
        self.risk_pct = risk_pct
        self.reason = "Initializing..."
        self.start_time = None
        
    def on_tick(self, market_info, current_temp, market_price, current_time):
        # 1. Set Start Time (First tick of the day)
        if self.start_time is None:
            self.start_time = current_time
            
        # 2. Wait Logic (120 mins)
        unlock_time = self.start_time + timedelta(minutes=120)
        if current_time < unlock_time:
            mins_left = int((unlock_time - current_time).total_seconds() / 60)
            self.reason = f"Waiting for timer ({mins_left}m left)"
            return "HOLD"
            
        # 3. Trade Logic (Trend No: Buy NO if Price 50-70)
        # Note: market_price is usually YES price.
        # So NO price = 100 - market_price.
        no_price = 100 - market_price
        
        if 50 < no_price < 70:
            self.reason = f"BUY SIGNAL! NO Price {no_price:.0f} in range 50-70"
            return "BUY_NO"
        else:
            self.reason = f"Watching NO Price {no_price:.0f} (Target: 50-70)"
            return "HOLD"

# --- Live Trader V5 ---
class LiveTraderV5:
    def __init__(self):
        self.strategy = SafeBaselineStrategy(risk_pct=0.50)
        self.file_states = {} # {filename: processed_rows}
        self.last_status_time = None
        self.launch_time = datetime.now()
        
        # API State
        self.balance = 0.0
        self.portfolio_value = 0.0 # Current Mark-to-Market Value
        self.daily_start_equity = 0.0 # Snapshot at 5 AM (Cash + Invested)
        self.last_reset_date = None
        self.spent_today = 0.0 # Track daily spend to enforce budget cap
        self.positions = {} # {ticker: {'qty': qty, 'cost': cost}}

    def check_control_flag(self):
        """
        Checks if trading is enabled via external file.
        Default to True if file doesn't exist.
        """
        try:
            if os.path.exists("trading_enabled.txt"):
                with open("trading_enabled.txt", "r") as f:
                    content = f.read().strip().lower()
                    return content == "true"
            else:
                # Create default enabled file
                with open("trading_enabled.txt", "w") as f:
                    f.write("true")
                return True
        except Exception as e:
            print(f"Error checking control flag: {e}")
            return True

    def update_status_file(self, status="RUNNING"):
        """
        Writes current status to JSON for the dashboard.
        """
        try:
            budget = self.daily_start_equity * self.strategy.risk_pct
            spent_pct = (self.spent_today / budget * 100) if budget > 0 else 0.0
            
            data = {
                "status": status,
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "strategy": self.strategy.name,
                "equity": self.get_total_equity(),
                "cash": self.balance,
                "pnl_today": 0.0, # TODO: Track daily PnL
                "trades_today": len(self.positions),
                "daily_budget": budget,
                "spent_today": self.spent_today,
                "spent_pct": spent_pct,
                "target_date": "Dec 17+"
            }
            with open("trader_status.json", "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error updating status file: {e}")

    def calculate_spent_today(self):
        """Reconstruct spent_today from trades.csv for the current day."""
        if not os.path.exists(TRADES_LOG_FILE): return 0.0
        
        total_spent = 0.0
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        try:
            with open(TRADES_LOG_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Timestamp format: 2025-12-13 07:29:49.839752
                    ts_str = row['timestamp']
                    if ts_str.startswith(today_str):
                        total_spent += float(row['cost'])
        except Exception as e:
            print(f"Error calculating spent_today: {e}")
            
        return total_spent
        
    def get_total_equity(self):
        """Calculate Total Equity = Cash + Portfolio Value (Mark-to-Market)."""
        return self.balance + self.portfolio_value

    def sync_api_state(self, force_reset_daily=False):
        """Fetch latest Balance and Positions from Kalshi."""
        try:
            with open(PRIVATE_KEY_PATH, 'rb') as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)
            
            current_balance, current_portfolio_value = get_balance(private_key)
            self.balance = current_balance
            self.portfolio_value = current_portfolio_value
            
            # Sync Positions (Still needed for logic/logging)
            raw_positions = get_positions(private_key)
            self.positions = {}
            for p in raw_positions:
                qty = abs(p.get('position', 0))
                if qty > 0:
                    # market_exposure is in cents
                    cost = p.get('market_exposure', 0) / 100.0
                    self.positions[p['ticker']] = {'qty': qty, 'cost': cost}

            # Daily Reset Logic (5 AM)
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            
            # Calculate Current Equity
            current_equity = self.get_total_equity()
            
            # If it's a new day (or first run), or forced reset
            if self.daily_start_equity == 0.0 or force_reset_daily:
                self.daily_start_equity = current_equity
                self.last_reset_date = today_str
                self.spent_today = self.calculate_spent_today() # Sync spend from logs
                print(f"  [BUDGET] Daily Start Equity set to ${self.daily_start_equity:.2f} (Cash: ${self.balance:.2f} + Portfolio: ${self.portfolio_value:.2f})")
                print(f"  [BUDGET] Spent Today: ${self.spent_today:.2f}")
                    
        except Exception as e:
            print(f"Error syncing API state: {e}")

    def get_active_log_files(self):
        """Get all market logs for MIN_MARKET_DATE and FUTURE dates only."""
        all_files = sorted(glob.glob(os.path.join(LOG_DIR, "market_data_*.csv")))
        active_files = []
        
        # USER REQUEST: Start trading from Dec 17th onwards
        MIN_MARKET_DATE = date(2025, 12, 17)
        
        for f in all_files:
            try:
                # Filename format: market_data_KXHIGHNY-25DEC16.csv
                basename = os.path.basename(f)
                ticker_date_part = basename.replace("market_data_KXHIGHNY-", "").replace(".csv", "")
                # Parse date: 25DEC16
                file_date = datetime.strptime(ticker_date_part, "%y%b%d").date()
                
                # Keep if date is >= MIN_MARKET_DATE
                if file_date >= MIN_MARKET_DATE:
                    active_files.append(f)
            except:
                pass
                
        return active_files

    def process_new_data(self, log_file):
        try:
            if log_file not in self.file_states:
                self.file_states[log_file] = 0
                print(f"Tracking new log file: {os.path.basename(log_file)}")
            
            processed_rows = self.file_states[log_file]
            
            # Read only new rows? 
            # For simplicity/robustness, read all and slice.
            # If file is huge, use seek/tell (optimization for later).
            df = pd.read_csv(log_file, on_bad_lines='skip')
            if df.empty: return
            
            if len(df) > processed_rows:
                new_data = df.iloc[processed_rows:]
                self.file_states[log_file] = len(df)
                
                # Process Ticks
                for index, row in new_data.iterrows():
                    self.on_tick(row)
                    
        except Exception as e:
            print(f"Error reading log {os.path.basename(log_file)}: {e}")

    def on_tick(self, row):
        ticker = row['market_ticker']
        # Parse timestamp
        try:
            current_time = pd.to_datetime(row['timestamp'])
        except:
            return

        yes_ask = row.get('implied_yes_ask', np.nan)
        no_ask = row.get('implied_no_ask', np.nan)
        
        if pd.isna(yes_ask) and pd.isna(no_ask): return
        
        # --- DATE FILTER: Trade ONLY Tomorrow's Market ---
        # Parse ticker date (e.g., KXHIGHNY-25DEC13)
        try:
            # Extract '25DEC13'
            date_part = ticker.split('-')[1]
            # Parse to datetime
            mkt_date = datetime.strptime(date_part, "%y%b%d").date()
            today = datetime.now().date()
            
            # If Market Date is Today (or past), SKIP.
            # We only want to invest in the "Newest" day (Tomorrow).
            if mkt_date <= today:
                return
        except:
            pass # If parse fails, assume safe or skip? Let's skip to be safe.
            return
        
        # Price for strategy (YES price)
        price = yes_ask if not pd.isna(yes_ask) else (100 - no_ask)
        
        # Strategy Logic
        action = self.strategy.on_tick(None, -999, price, current_time)
        
        # Execute?
        if action != "HOLD":
            # Only trade if data is FRESH (arrived after launch)
            if current_time >= self.launch_time:
                self.execute_trade(action, ticker, yes_ask, no_ask, current_time)

    def execute_trade(self, action, ticker, yes_ask, no_ask, timestamp):
        # 1. Check Existing Position (Prevent Double-Buy)
        if ticker in self.positions:
            return # Already hold this ticker
            
        # 2. Determine Price & Side
        if action == "BUY_YES":
            if pd.isna(yes_ask): return
            price = yes_ask
            side = 'yes'
        elif action == "BUY_NO":
            if pd.isna(no_ask): return
            price = no_ask
            side = 'no'
        else: return
        
        # 3. Budget Check (Based on Daily Start Equity)
        # Risk Management: Spend risk_pct of DAILY START EQUITY
        # This aligns with the backtest: Risk is based on Total Account Value.
        
        budget = self.daily_start_equity * self.strategy.risk_pct
        
        # DEDUCT SPENT TODAY
        available_budget = budget - self.spent_today
        if available_budget <= 0:
            # Silent return if budget is exhausted (to avoid log spam)
            # Only print if it's the first time we hit the cap? No, just silent.
            return

        cost_per_share = price / 100.0
        
        if cost_per_share <= 0: return
        qty = int(available_budget // cost_per_share)
        
        if qty <= 0: return
        
        total_cost = qty * cost_per_share
        
        # Final Affordability Check (Real Current Balance)
        if self.balance < total_cost:
            print(f"❌ SKIPPING: Insufficient Funds (${self.balance:.2f} < ${total_cost:.2f})")
            return

        # 4. Execute Real Order
        success = place_real_order(ticker, qty, price, side)
        
        if success:
            # Log to CSV
            self.log_trade(timestamp, ticker, action, price, qty, total_cost)
            # Update Internal State (Optimistic)
            self.balance -= total_cost
            self.spent_today += total_cost
            self.positions[ticker] = {'qty': qty, 'cost': total_cost}
        else:
            print(f"⚠️ INTERNAL: Trade failed for {ticker}. Not updating internal state.")

    def log_trade(self, timestamp, ticker, action, price, qty, cost):
        file_exists = os.path.isfile(TRADES_LOG_FILE)
        try:
            with open(TRADES_LOG_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["timestamp", "strategy", "ticker", "action", "price", "qty", "cost"])
                writer.writerow([timestamp, self.strategy.name, ticker, action, price, qty, cost])
                print(f"  [LOG] Trade saved to {TRADES_LOG_FILE}")
        except Exception as e:
            print(f"Error logging trade: {e}")

    def print_status(self):
        print(f"\n--- Status @ {datetime.now().strftime('%H:%M:%S')} ---")
        print(f"Strategy: {self.strategy.name}")
        print(f"Thought: {self.strategy.reason}")
        print(f"Daily Budget Base (Equity): ${self.daily_start_equity:.2f}")
        print(f"Spent Today: ${self.spent_today:.2f} / ${self.daily_start_equity * self.strategy.risk_pct:.2f}")
        print(f"Real Balance: ${self.balance:.2f}")
        print(f"Total Equity: ${self.get_total_equity():.2f}")
        print(f"Active Positions: {len(self.positions)}")
        for ticker, data in self.positions.items():
            print(f"  - {ticker}: {data['qty']} contracts (Cost: ${data['cost']:.2f})")
        print("---------------------------------------------------\n")

    def run(self):
        print("=== Live Trader V5 (Robust Execution / Aggressive Limits) ===")
        print("Syncing Initial State...")
        self.sync_api_state(force_reset_daily=True) # Initialize Daily Balance
        print(f"Initial Balance: ${self.balance:.2f}")
        print(f"Existing Positions: {len(self.positions)}")
        
        # Initial Status Update
        self.update_status_file("STARTING")

        while True:
            # 0. Check Control Flag
            if not self.check_control_flag():
                print("Trading PAUSED by control flag. Waiting...", end='\r')
                self.update_status_file("PAUSED")
                time.sleep(10)
                continue

            self.update_status_file("RUNNING")

            now = datetime.now()
            
            # 5 AM Reset Logic
            today_str = now.strftime('%Y-%m-%d')
            if self.last_reset_date != today_str and now.hour >= 5:
                print("🌅 5:00 AM Reached! Resetting Daily Risk Budget & Timer...")
                self.sync_api_state(force_reset_daily=True)
                self.strategy.start_time = None # Reset Timer for new day
            
            # 1. Sync Logs (Handled by external script, we just read)
            active_files = self.get_active_log_files()
            
            # 2. Process Data
            for log_file in active_files:
                self.process_new_data(log_file)
                
            # 3. Periodic Status & State Sync (every 60s)
            if self.last_status_time is None or (now - self.last_status_time).total_seconds() >= 60:
                self.sync_api_state() # Regular sync (updates balance, keeps daily_start unless forced)
                self.print_status()
                self.last_status_time = now
                
            time.sleep(1)

if __name__ == "__main__":
    trader = LiveTraderV5()
    trader.run()
