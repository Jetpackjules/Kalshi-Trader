import asyncio
import base64
import json
import time
import websockets
import requests
import csv
import os
import uuid
import glob
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# --- Configuration ---
LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
PORTFOLIO_FILE = "portfolio_state.json"
INITIAL_CAPITAL_PER_STRAT = 2.00 # Increased to $2.00 to allow trading
DRY_RUN = False # Set to False to ENABLE REAL TRADING

# API Config
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\kalshi_prod_private_key.pem"
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

    return base64.b64encode(signature).decode('utf-8')

def create_headers(private_key, method: str, path: str) -> dict:
    timestamp = str(int(time.time() * 1000))
    msg_string = timestamp + method + path.split('?')[0]
    signature = sign_pss_text(private_key, msg_string)
    return base64.b64encode(signature).decode('utf-8')

def create_headers(private_key, method: str, path: str) -> dict:
    timestamp = str(int(time.time() * 1000))
    msg_string = timestamp + method + path.split('?')[0]
    signature = sign_pss_text(private_key, msg_string)
    return base64.b64encode(signature).decode('utf-8')

def create_headers(private_key, method: str, path: str) -> dict:
    timestamp = str(int(time.time() * 1000))
    msg_string = timestamp + method + path.split('?')[0]
    signature = sign_pss_text(private_key, msg_string)
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

def get_positions(private_key):
    """Fetch current portfolio positions."""
    path = "/trade-api/v2/portfolio/positions"
    method = "GET"
    headers = create_headers(private_key, method, path)
    
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Return list of dicts with ticker, position, and market_exposure
            return data.get("market_positions", [])
        else:
            print(f"Error fetching positions: {response.status_code} {response.text}")
            return []
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []

def get_settlements(private_key):
    """Fetch recent settlements."""
    path = "/trade-api/v2/portfolio/settlements"
    method = "GET"
    headers = create_headers(private_key, method, path)
    
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("settlements", [])
        else:
            print(f"Error fetching settlements: {response.status_code} {response.text}")
            return []
    except Exception as e:
        print(f"Error fetching settlements: {e}")
        return []

def get_balance(private_key):
    """Fetch current available balance."""
    path = "/trade-api/v2/portfolio/balance"
    method = "GET"
    headers = create_headers(private_key, method, path)
    
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Balance is in cents usually? Let's check.
            # Documentation says balance is in cents.
            return data.get("balance", 0) / 100.0
        else:
            print(f"Error fetching balance: {response.status_code} {response.text}")
            return 0.0
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return 0.0

def place_real_order(ticker, count, price, side):
    """Executes a REAL order on Kalshi."""
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except Exception as e:
        print(f"API Error: {e}")
        return False

    path = "/trade-api/v2/portfolio/orders"
    method = "POST"
    order_id = str(uuid.uuid4())
    
    payload = {
        "action": "buy", # We only BUY (either YES or NO contracts)
        "count": count,
        "side": side, # 'yes' or 'no'
        "ticker": ticker,
        "type": "limit",
        "yes_price" if side == 'yes' else "no_price": price,
        "client_order_id": order_id
    }
    
    headers = create_headers(private_key, method, path)
    try:
        response = requests.post(f"{API_URL}{path}", headers=headers, json=payload)
        if response.status_code == 201:
            print(f"✅ REAL TRADE EXECUTED: {ticker} {side.upper()} @ {price} (ID: {order_id})")
            return True
        else:
            print(f"❌ TRADE FAILED: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"❌ TRADE ERROR: {e}")
        return False

# --- Strategies ---
class Strategy:
    def __init__(self, name, risk_pct=0.8):
        self.name = name
        self.risk_pct = risk_pct
        self.start_time = None
        self.reason = "Initializing..."
        
    def start_new_day(self, first_timestamp):
        self.start_time = first_timestamp
        self.reason = "New Day Started"
        
    def on_tick(self, market, current_temp, market_price, current_time):
        return "HOLD"

class ParametricStrategy(Strategy):
    def __init__(self, name, wait_minutes, risk_pct, logic_type="trend_no", greedy=False):
        super().__init__(name, risk_pct)
        self.wait_minutes = wait_minutes
        self.logic_type = logic_type
        self.greedy = greedy
        
    def on_tick(self, market, current_temp, market_price, current_time):
        if self.start_time is None: 
            self.reason = "Waiting for day start"
            return "HOLD"
            
        unlock_time = self.start_time + timedelta(minutes=self.wait_minutes)
        if current_time < unlock_time:
            mins_left = int((unlock_time - current_time).total_seconds() / 60)
            self.reason = f"Waiting for timer ({mins_left}m left)"
            return "HOLD"
            
        if self.logic_type == "trend_no":
            no_price = 100 - market_price
            if 50 < no_price < 70: 
                self.reason = f"BUY SIGNAL! Price {no_price:.0f} in range 50-70"
                return "BUY_NO"
            else:
                self.reason = f"Watching Price {no_price:.0f} (Target: 50-70)"
                
        return "HOLD"

class MeanReversionStrategy(Strategy):
    """
    Fades extreme moves.
    """
    def __init__(self, name, risk_pct=0.5, upper_bound=80, lower_bound=20):
        super().__init__(name, risk_pct)
        self.reason = "Initializing..."
        self.greedy = True # Radical strategy -> Greedy budget
        self.wait_minutes = 0 # No wait time
        self.upper_bound = upper_bound
        self.lower_bound = lower_bound
        
    def on_tick(self, market, current_temp, market_price, current_time):
        no_price = 100 - market_price
        
        # Overbought NO (Price > Upper) -> Buy YES (Fade)
        if no_price > self.upper_bound: 
            self.reason = f"FADE SIGNAL! Price {no_price:.0f} > {self.upper_bound}. Buying YES."
            return "BUY_YES"
            
        # Oversold NO (Price < Lower) -> Buy NO (Fade)
        if no_price < self.lower_bound: 
            self.reason = f"FADE SIGNAL! Price {no_price:.0f} < {self.lower_bound}. Buying NO."
            return "BUY_NO"
            
        self.reason = f"Watching Price {no_price:.0f} (Range: {self.lower_bound}-{self.upper_bound})"
        return "HOLD"

class CloserStrategy(Strategy):
    """
    Enters at 3 PM (15:00) if price is uncertain (40-60).
    """
    def __init__(self, name, risk_pct=0.5):
        super().__init__(name, risk_pct)
        self.reason = "Initializing..."
        self.greedy = False
        
    def on_tick(self, market, current_temp, market_price, current_time):
        # Check Time: 15:00 - 15:59
        if current_time.hour != 15: 
            self.reason = f"Waiting for 3 PM (Current: {current_time.strftime('%H:%M')})"
            return "HOLD"
        
        no_price = 100 - market_price
        # Uncertain Range?
        if 40 < no_price < 60: 
            self.reason = f"BUY SIGNAL! Price {no_price:.0f} in range 40-60"
            return "BUY_NO"
            
        self.reason = f"Watching Price {no_price:.0f} (Target: 40-60)"
        return "HOLD"

# --- Virtual Portfolio ---
class VirtualPortfolio:
    def __init__(self, strategy_name, initial_capital):
        self.strategy_name = strategy_name
        self.cash = initial_capital
        self.holdings = [] 
        self.trades = []
        self.daily_start_cash = initial_capital
        self.spent_today = 0.0

    def to_dict(self):
        return {
            'strategy_name': self.strategy_name,
            'cash': self.cash,
            'holdings': self.holdings,
            'trades': self.trades,
            'daily_start_cash': self.daily_start_cash,
            'spent_today': self.spent_today
        }

    def from_dict(self, data):
        self.cash = data.get('cash', self.cash)
        self.holdings = data.get('holdings', [])
        self.trades = data.get('trades', [])
        self.daily_start_cash = data.get('daily_start_cash', self.cash)
        self.spent_today = data.get('spent_today', 0.0)

    def spend(self, amount):
        if amount > self.cash:
            return False
        return True

    def execute_buy(self, ticker, side, qty, price, cost, timestamp):
        self.cash -= cost
        self.spent_today += cost
        self.holdings.append({
            'ticker': ticker,
            'side': side,
            'qty': qty,
            'price': price,
            'cost': cost,
            'time': timestamp
        })
        self.trades.append({
            'time': timestamp,
            'action': f"BUY_{side.upper()}",
            'ticker': ticker,
            'qty': qty,
            'price': price,
            'cost': cost
        })
        print(f"[{self.strategy_name}] BUY {ticker} ({side.upper()}) x{qty} @ {price}¢ | Cost: ${cost:.2f} | Cash Left: ${self.cash:.2f}")

# --- Live Trader Engine ---
class LiveTraderV2:
    def __init__(self):
        self.state_file = "portfolio_state.json"
        self.strategies = [
            # 1. Safe Baseline (Wait 150m | Risk 50%)
            ParametricStrategy("Safe Baseline (Wait 150m | Risk 50%)", 150, 0.5, "trend_no", greedy=False),
            
            # 2. Mean Reversion Strict (Fade >85/<15 | Risk 20%)
            MeanReversionStrategy("Mean Reversion (Fade >85/<15 | Risk 20%)", risk_pct=0.2, upper_bound=85, lower_bound=15)
        ]
        self.portfolios = {s.name: VirtualPortfolio(s.name, INITIAL_CAPITAL_PER_STRAT) for s in self.strategies}
        self.load_state() # Load if exists
        
        self.file_states = {} # {filename: {'processed_rows': 0, 'first_timestamp': None}}
        self.last_status_time = None
        self.launch_time = datetime.now() - timedelta(seconds=10) # Allow small buffer for startup
        
        # SAFETY: Track globally traded tickers to prevent double-spending on restart
        self.real_positions = {} # {ticker: qty} from Kalshi
        self.global_blacklist = set() # Tickers with mismatches (DO NOT TRADE)
        self.sync_real_positions()
        self.reconcile_state()
        
        print(f"System Launch Time: {self.launch_time}")

    def sync_real_positions(self):
        """Fetch ACTUAL positions from Kalshi."""
        print("Syncing REAL positions from Kalshi...")
        try:
            with open(PRIVATE_KEY_PATH, 'rb') as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)
            
            positions = get_positions(private_key)
            # Store full details: qty and cost
            for pos in positions:
                qty = abs(pos.get("position", 0))
                if qty > 0:
                    ticker = pos.get("ticker")
                    # market_exposure is in cents, convert to dollars
                    cost = pos.get("market_exposure", 0) / 100.0
                    self.real_positions[ticker] = {'qty': qty, 'cost': cost}
                    print(f"  [REAL] Found {qty} contracts of {ticker} (Cost: ${cost:.2f})")
        except Exception as e:
            print(f"Error syncing positions: {e}")

    def sync_wallet_balance(self):
        """Sync Virtual Cash with Real Wallet Balance."""
        print("Syncing Wallet Balance...")
        try:
            with open(PRIVATE_KEY_PATH, 'rb') as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)
            
            real_balance = get_balance(private_key)
            print(f"  [REAL] Wallet Balance: ${real_balance:.2f}")
            
            # Distribute equally among strategies
            # OR: Should we keep separate cash piles?
            # For simplicity, let's split it.
            # If we have 2 strategies, each gets 50%.
            
            share = real_balance / len(self.strategies)
            for name, p in self.portfolios.items():
                p.cash = share
                # Also update daily_start_cash to avoid confusing PnL
                # p.daily_start_cash = share 
                # Actually, daily_start_cash should track session start.
                # If we restart mid-day, PnL might reset. That's acceptable.
                
            print(f"  [SYNC] Updated Virtual Cash to ${share:.2f} per strategy")
            
        except Exception as e:
            print(f"Error syncing wallet: {e}")

    def reconcile_state(self):
        """Compare Local vs Real state. ABORT on mismatches."""
        print("\n=== RECONCILIATION REPORT ===")
        print(f"{'Ticker':<30} | {'Real':<5} | {'Local':<5} | {'Status':<10}")
        print("-" * 60)
        
        # 1. Sum Local Holdings
        local_holdings = {}
        for name, p in self.portfolios.items():
            for h in p.holdings:
                ticker = h['ticker']
                local_holdings[ticker] = local_holdings.get(ticker, 0) + h['qty']
                
        # 2. Compare with Real
        # self.real_positions is now a dict of {ticker: {'qty': qty, 'cost': cost}}
        real_tickers = set(self.real_positions.keys())
        all_tickers = sorted(list(real_tickers | set(local_holdings.keys())))
        mismatches = []
        
        for ticker in all_tickers:
            real_data = self.real_positions.get(ticker, {'qty': 0, 'cost': 0})
            real_qty = real_data['qty']
            local_qty = local_holdings.get(ticker, 0)
            
            status = "OK"
            if real_qty != local_qty:
                status = "MISMATCH"
                mismatches.append(ticker)
            
            if real_qty > 0 or local_qty > 0:
                print(f"{ticker:<30} | {real_qty:<5} | {local_qty:<5} | {status:<10}")

        print("-" * 60)
        
        if mismatches:
            # AUTO-ADOPT: If local state is empty (Fresh Start), adopt real positions
            total_local = sum(local_holdings.values())
            if total_local == 0:
                print("⚠️ Fresh Start Detected: Adopting Real Positions into Local State...")
                default_strat = self.strategies[0].name
                p = self.portfolios[default_strat]
                
                for ticker, data in self.real_positions.items():
                    qty = data['qty']
                    cost = data['cost'] # Total cost in dollars
                    
                    # Calculate avg price
                    price = 0
                    if qty > 0:
                        price = int((cost / qty) * 100) # Price in cents
                    
                    p.holdings.append({
                        'ticker': ticker,
                        'side': 'yes' if 'yes' in ticker.lower() else 'no', 
                        'qty': qty,
                        'price': price,
                        'cost': cost,
                        'time': datetime.now()
                    })
                    
                    # DO NOT DEDUCT COST HERE. 
                    # We will sync cash directly from the wallet in the next step.
                    
                    print(f"  [ADOPT] Imported {ticker} ({qty}) @ {price}¢ | Cost: ${cost:.2f}")
                
                self.sync_wallet_balance() # SYNC CASH NOW
                self.save_state()
                print("✅ Positions Adopted. Restarting Reconciliation...")
                self.reconcile_state() # Re-run to confirm
                return

            print(f"❌ CRITICAL ERROR: Found {len(mismatches)} position mismatches!")
            print("The bot cannot safely continue because Local State != Real State.")
            print("Please manually resolve these positions or clear 'portfolio_state.json' if appropriate.")
            raise RuntimeError("Position Mismatch Detected. Aborting startup.")
        else:
            print("✅ State Reconciled. System Safe.")

    def log_trade_to_csv(self, timestamp, strategy_name, ticker, action, price, qty, cost):
        """Log trade to a persistent CSV file."""
        log_file = "trades.csv"
        file_exists = os.path.isfile(log_file)
        
        try:
            with open(log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["timestamp", "strategy", "ticker", "action", "price", "qty", "cost"])
                
                writer.writerow([timestamp, strategy_name, ticker, action, price, qty, cost])
                print(f"  [LOG] Trade saved to {log_file}")
        except Exception as e:
            print(f"Error logging trade: {e}")

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    for name, p_data in data.items():
                        if name in self.portfolios:
                            self.portfolios[name].from_dict(p_data)
                print(f"Loaded portfolio state from {self.state_file}")
                self.settle_expired_holdings() # Check for settlements on load
            except Exception as e:
                print(f"Error loading state: {e}")

    def save_state(self):
        data = {name: p.to_dict() for name, p in self.portfolios.items()}
        try:
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=4, default=str)
        except Exception as e:
            print(f"Error saving state: {e}")

    def settle_expired_holdings(self):
        print("Checking for settlements via API...")
        try:
            with open(PRIVATE_KEY_PATH, 'rb') as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)
            
            settlements = get_settlements(private_key)
            # Create a lookup: {ticker: settlement_data}
            settled_tickers = {s['ticker']: s for s in settlements}
            
            for name, p in self.portfolios.items():
                if not p.holdings: continue
                
                new_holdings = []
                for h in p.holdings:
                    ticker = h['ticker']
                    
                    if ticker in settled_tickers:
                        s = settled_tickers[ticker]
                        # Calculate PnL based on API data
                        # 'revenue' is in cents? Sample says 100. 'no_total_cost' is 59.
                        # Wait, revenue is total payout.
                        # If we held YES and market result is NO, revenue is 0.
                        # If we held NO and market result is NO, revenue is 100 * count.
                        
                        # Actually, let's just use the 'revenue' field if it matches our trade?
                        # But settlements list is aggregated per ticker?
                        # "no_count": 1, "no_total_cost": 59, "revenue": 100
                        
                        # We need to know if *our specific holding* is covered.
                        # Since we only hold one position per ticker (enforced by logic),
                        # we can assume if the ticker is in settlements, it's settled.
                        
                        # Determine payout per share
                        market_result = s.get('market_result', 'unknown')
                        payout = 0
                        if market_result == 'yes':
                            payout = 100
                        elif market_result == 'no':
                            payout = 100
                        # Wait, payout depends on which side won.
                        # If result is 'no', NO shares pay 100, YES shares pay 0.
                        
                        exit_price = 0
                        if h['side'] == 'yes' and market_result == 'yes': exit_price = 100
                        elif h['side'] == 'no' and market_result == 'no': exit_price = 100
                        elif market_result == 'void': exit_price = h['price'] # Refund?
                        
                        value = h['qty'] * (exit_price / 100.0)
                        p.cash += value
                        pnl = value - h['cost']
                        print(f"[{name}] API SETTLED {ticker} (Result: {market_result.upper()}) | PnL: ${pnl:+.2f} | New Cash: ${p.cash:.2f}")
                        continue
                    
                    new_holdings.append(h)
                p.holdings = new_holdings
            self.save_state()
            
        except Exception as e:
            print(f"Error checking settlements: {e}")

    def run(self):
        print("=== Live Trader V2 Started ===")
        print(f"Strategies: {[s.name for s in self.strategies]}")
        print(f"Initial Capital: ${INITIAL_CAPITAL_PER_STRAT} per strategy")
        print(f"Mode: {'DRY RUN (Simulation)' if DRY_RUN else 'REAL TRADING (Live)'}")

        while True:
            active_files = self.get_active_log_files()
            if not active_files:
                print("Waiting for log files...", end='\r')
                time.sleep(5)
                continue

            # Process all active files
            for log_file in active_files:
                self.process_new_data(log_file)
                
            # Status Update (Global, based on system time or last processed time)
            if self.last_status_time is None:
                self.last_status_time = datetime.now()
            
            if (datetime.now() - self.last_status_time).total_seconds() >= 60:
                self.print_status_update(datetime.now())
                self.last_status_time = datetime.now()

            time.sleep(1) 

    def get_active_log_files(self):
        """Get all market logs for TODAY and FUTURE dates only."""
        files = sorted(glob.glob(os.path.join(LOG_DIR, "market_data_*.csv")))
        if not files: return []
        
        active_files = []
        today_str = datetime.now().strftime("%y%b%d").upper() # e.g., 25DEC12
        
        # Parse today's date object for comparison
        try:
            today_date = datetime.strptime(today_str, "%y%b%d").date()
        except ValueError:
            return files[-2:] # Fallback
            
        for f in files:
            basename = os.path.basename(f)
            # Expected format: market_data_KXHIGHNY-25DEC12.csv
            try:
                # Extract date part: 25DEC12
                parts = basename.split('-')
                if len(parts) < 2: continue
                date_part = parts[-1].replace('.csv', '')
                
                file_date = datetime.strptime(date_part, "%y%b%d").date()
                
                # Keep if file_date >= today_date
                if file_date >= today_date:
                    active_files.append(f)
            except ValueError:
                continue # Skip files with unparseable dates
                
        return active_files

    def process_new_data(self, log_file):
        if log_file not in self.file_states:
            print(f"\nTracking new log file: {os.path.basename(log_file)}")
            self.file_states[log_file] = {'processed_rows': 0, 'first_timestamp': None}
            self.settle_expired_holdings() # Check settlements when new file appears
            
        state = self.file_states[log_file]
        
        try:
            df = pd.read_csv(log_file, on_bad_lines='skip')
            if df.empty: return
            
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            if state['first_timestamp'] is None:
                state['first_timestamp'] = df['timestamp'].iloc[0]
                # print(f"Start Time for {os.path.basename(log_file)}: {state['first_timestamp']}")
                for s in self.strategies:
                    s.start_new_day(state['first_timestamp'])

            if len(df) > state['processed_rows']:
                new_data = df.iloc[state['processed_rows']:]
                state['processed_rows'] = len(df)
                for index, row in new_data.iterrows():
                    self.on_tick(row)
                    
        except Exception as e:
            print(f"Error reading log {os.path.basename(log_file)}: {e}")

    def on_tick(self, row):
        ticker = row['market_ticker']
        current_time = row['timestamp']
        yes_ask = row.get('implied_yes_ask', np.nan)
        no_ask = row.get('implied_no_ask', np.nan)
        
        market_info = self.get_market_details(ticker)
        
        for strategy in self.strategies:
            portfolio = self.portfolios[strategy.name]
            
            if pd.isna(yes_ask) and pd.isna(no_ask): continue
            price_for_strat = yes_ask if not pd.isna(yes_ask) else (100 - no_ask)
            
            action = strategy.on_tick(market_info, -999, price_for_strat, current_time)
            
            # ONLY execute if the data is NEW (arrived after script start)
            # We allow strategy state to update on old data, but not trade.
            if action != "HOLD":
                if current_time >= self.launch_time:
                    self.execute_trade(strategy, portfolio, action, ticker, yes_ask, no_ask, current_time)
                # else:
                #     print(f"Skipping historical trade signal for {strategy.name} at {current_time}")

    def print_status_update(self, current_time):
        print(f"\n--- Status Update @ {current_time.strftime('%H:%M:%S')} ---")
        
        for strategy in self.strategies:
            p = self.portfolios[strategy.name]
            
            # Simplified status since we have multiple markets
            status_str = "RUNNING"
            
            pnl_session = p.cash - p.daily_start_cash
            
            print(f"  [{strategy.name}]")
            print(f"    Thought: {getattr(strategy, 'reason', '...')}")
            print(f"    Cash: ${p.cash:.2f} | Session PnL: ${pnl_session:+.2f} | Trades: {len(p.trades)}")
            
            if p.holdings:
                print("    Active Bets:")
                for h in p.holdings:
                    print(f"      - {h['ticker']} ({h['side'].upper()}): {h['qty']} contracts @ {h['price']}¢ (Cost: ${h['cost']:.2f})")
            else:
                print("    Active Bets: None")
        print("---------------------------------------------------\n")

    def execute_trade(self, strategy, portfolio, action, ticker, yes_ask, no_ask, timestamp):
        # 1. Prevent Over-Trading (One Bet Per Ticker)
        # Check Strategy Portfolio
        for h in portfolio.holdings:
            if h['ticker'] == ticker:
                return # Already have a position
        
        # Check Global Safety List (Real Positions)
        if ticker in self.global_blacklist:
            # print(f"  [SAFETY] Skipping {ticker} - State Mismatch (Blocked).")
            return

        # Determine Price
        if action == "BUY_YES":
            if pd.isna(yes_ask): return
            price = yes_ask
            side = 'yes'
        elif action == "BUY_NO":
            if pd.isna(no_ask): return
            price = no_ask
            side = 'no'
        else: return

        # Budget Logic (Equity-Based)
        holdings_value = sum(h['cost'] for h in portfolio.holdings)
        total_equity = portfolio.cash + holdings_value
        
        daily_budget = total_equity * strategy.risk_pct
        
        if strategy.greedy:
            # Greedy: Spend risk_pct of TOTAL EQUITY (but limited by available cash)
            target_spend = daily_budget
            max_spend = min(target_spend, portfolio.cash)
        else:
            # Safe: Cap total spend at daily_budget
            if holdings_value >= daily_budget: return
            available_to_spend = daily_budget - holdings_value
            max_spend = min(available_to_spend, portfolio.cash)
            
        # Qty
        qty = int(max_spend // (price / 100.0))
        if qty <= 0: return
        
        cost = qty * (price / 100.0)
        
        if qty > 0:
            # Spend from Wallet (Check Virtual Cash)
            if not portfolio.spend(cost):
                return # Not enough virtual cash
            
            # REAL EXECUTION
            if not DRY_RUN:
                # Check Real Balance First
                try:
                    with open(PRIVATE_KEY_PATH, 'rb') as f:
                        private_key = serialization.load_pem_private_key(f.read(), password=None)
                    real_balance = get_balance(private_key)
                    
                    if real_balance < cost:
                        print(f"❌ SKIPPING TRADE: Insufficient Real Balance (${real_balance:.2f} < ${cost:.2f})")
                        return
                except:
                    pass # Proceed if balance check fails (let order fail naturally)

                success = place_real_order(ticker, qty, price, side)
                if success:
                    # Update Real Positions (Optimistic)
                    # Need to update the dict structure
                    current_data = self.real_positions.get(ticker, {'qty': 0, 'cost': 0.0})
                    new_qty = current_data['qty'] + qty
                    new_cost = current_data['cost'] + cost
                    self.real_positions[ticker] = {'qty': new_qty, 'cost': new_cost}
                    
                    self.log_trade_to_csv(timestamp, strategy.name, ticker, action, price, qty, cost)
                    
                    # ONLY UPDATE VIRTUAL PORTFOLIO IF REAL TRADE SUCCEEDS
                    portfolio.execute_buy(ticker, side, qty, price, cost, timestamp)
                    self.save_state()
            else:
                print(f"  [DRY RUN] Would have placed REAL order for {ticker} {side.upper()} @ {price}")
                self.log_trade_to_csv(timestamp, strategy.name, ticker, action, price, qty, cost)
                # In Dry Run, always update virtual
                portfolio.execute_buy(ticker, side, qty, price, cost, timestamp)
                self.save_state()
                self.log_trade_to_csv(timestamp, strategy.name, ticker, action, price, qty, cost)
                # In Dry Run, always update virtual
                portfolio.execute_buy(ticker, side, qty, price, cost, timestamp)
                self.save_state()

    def get_market_details(self, ticker):
        try:
            parts = ticker.split('-')
            suffix = parts[-1]
            type_char = suffix[0]
            val = float(suffix[1:])
            if type_char == 'T': return {'strike_type': 'greater', 'floor_strike': val, 'cap_strike': None}
            else: return {'strike_type': 'less', 'floor_strike': None, 'cap_strike': val}
        except:
            return {}

if __name__ == "__main__":
    trader = LiveTraderV2()
    trader.run()
