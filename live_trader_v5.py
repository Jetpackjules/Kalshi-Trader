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
import math
from collections import defaultdict
from datetime import datetime, timedelta, date
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# --- Configuration ---
LOG_DIR = "market_logs"
TRADES_LOG_FILE = "trades.csv"
ENABLE_TIME_CONSTRAINTS = True

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
    aggressive_price = min(99, int(price + 1))
    
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

# --- Helper Functions ---
def calculate_convex_fee(price, qty):
    """0.07 * qty * p * (1-p) - Kalshi style fee"""
    p = price / 100.0
    raw_fee = 0.07 * qty * p * (1 - p)
    fee = math.ceil(raw_fee * 100) / 100.0
    return fee

def best_yes_bid(ms):
    yb = ms.get('yes_bid', np.nan)
    na = ms.get('no_ask', np.nan)
    if not pd.isna(yb):
        return yb
    if not pd.isna(na):
        return 100 - na
    return np.nan

def best_yes_ask(ms):
    return ms.get('yes_ask', np.nan)

# --- Complex Strategy Base Class ---
class ComplexStrategy:
    def __init__(self, name, risk_pct=0.5):
        self.name = name
        self.risk_pct = risk_pct
        self.reason = "Initializing..."
        
    def on_market_update(self, ticker, market_state, current_time, inventory, active_orders, spendable_cash, idx=0):
        return None

# --- Implementation of Strategy 2.5 (V2 Refined) ---
class InventoryAwareMarketMaker(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5, max_inventory=50, inventory_penalty=0.5, max_offset=2, alpha=0.1, 
                 margin_cents=4.0, scaling_factor=4.0, max_notional_pct=0.05, max_loss_pct=0.02):
        super().__init__(name, risk_pct)
        self.max_inventory = max_inventory
        self.inventory_penalty = inventory_penalty
        self.max_offset = max_offset
        self.alpha = alpha
        
        # New configurable params
        self.margin_cents = margin_cents
        self.scaling_factor = scaling_factor
        self.max_notional_pct = max_notional_pct
        self.max_loss_pct = max_loss_pct
        
        self.fair_prices = {} 
        self.last_quote_time = {} 
        self.last_mid_snapshot = {} 

    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        yes_ask = best_yes_ask(market_state)
        no_ask = market_state.get('no_ask', np.nan)
        yes_bid = best_yes_bid(market_state)
        
        # Calculate Best Bid/Ask
        if pd.isna(yes_ask) or pd.isna(yes_bid):
            return None # Can't price without ask/bid

        mid = (yes_bid + yes_ask) / 2.0
        self.last_mid_snapshot[ticker] = mid
        self.last_quote_time[ticker] = current_time

        # --- PHASE 7: VAMR SIGNAL (Volatility-Adjusted Mean Reversion) ---
        hist = self.fair_prices.get(ticker, [])
        hist.append(mid)
        if len(hist) > 20: hist.pop(0)
        self.fair_prices[ticker] = hist
        
        if len(hist) < 20: return None # Warmup
        
        mean_price = np.mean(hist)
        
        # --- PHASE 8 FIX: VAMR PROBABILITY (Mean-Based) ---
        fair_prob = mean_price / 100.0
        
        # --- PASSIVE ENTRY: Price at Mid (Maker) ---
        # We try to capture the spread by sitting at the mid.
        price_to_pay_yes = int(mid)
        price_to_pay_no = int(100 - mid)
        
        # Check Long YES edge
        edge_yes = fair_prob - (price_to_pay_yes / 100.0)
        
        # Check Long NO edge
        # Buying NO short YES is 1 - fair_prob vs no_ask
        edge_no = (1.0 - fair_prob) - (price_to_pay_no / 100.0)
        
        edge = 0
        action = None
        price_to_pay = 0
        
        if edge_yes > 0:
            edge = edge_yes
            action = 'BUY_YES'
            price_to_pay = price_to_pay_yes
        elif edge_no > 0:
            edge = edge_no
            action = 'BUY_NO'
            price_to_pay = price_to_pay_no
            
        if action is None: return None
        
        # --- PHASE 8 FIX: FEE/SPREAD GATE ---
        dummy_qty = 10
        fee_est = calculate_convex_fee(price_to_pay, dummy_qty) / dummy_qty # $ per contract
        fee_cents = fee_est * 100
        
        required_edge_cents = fee_cents + self.margin_cents # Fee + Margin
        
        if (edge * 100) < required_edge_cents: return None
        
        # --- PHASE 9: SCALABLE SIZING (Smart Sizing) ---
        
        edge_cents = edge * 100.0

        # use continuous per-contract fee estimate (no rounding artifacts)
        p = price_to_pay / 100.0
        fee_per_contract = 0.07 * p * (1 - p)   # dollars per contract (approx)
        fee_cents = fee_per_contract * 100.0

        edge_after_fee = edge_cents - fee_cents - self.margin_cents
        if edge_after_fee <= 0:
            return None

        scale = min(1.0, edge_after_fee / self.scaling_factor)

        max_notional = spendable_cash * self.max_notional_pct
        max_loss = spendable_cash * self.max_loss_pct

        price_unit = price_to_pay / 100.0
        cost_unit = price_unit + fee_per_contract

        qty_by_notional = int(max_notional / cost_unit) if cost_unit > 0 else 0
        qty_by_loss = int(max_loss / cost_unit) if cost_unit > 0 else 0

        base_qty = min(qty_by_notional, qty_by_loss)
        if base_qty <= 0:
            return None

        current_inv = inventories['YES'] if action == 'BUY_YES' else inventories['NO']
        room = self.max_inventory - current_inv
        if room <= 0:
            return None

        inv_penalty = 1.0 / (1.0 + current_inv / 200.0)

        qty = int(base_qty * scale * inv_penalty)
        qty = max(1, min(qty, room))
        
        # Re-gate with actual fee (rounding check)
        fee_real = calculate_convex_fee(price_to_pay, qty)
        fee_cents_real = (fee_real / qty) * 100.0
        
        edge_after_fee_real = edge_cents - fee_cents_real - self.margin_cents
        if edge_after_fee_real <= 0:
            return None
        
        orders = []
        
        # --- EXECUTION ---
        if action == 'BUY_YES':
            # INVARIANT: Cannot buy YES if we hold NO
            if inventories['NO'] > 0: return None
            
            orders.append({'action': 'BUY_YES', 'ticker': ticker, 'qty': qty, 'price': yes_ask, 'expiry': current_time + timedelta(seconds=15), 'source': 'MM', 'time': current_time})
        
        elif action == 'BUY_NO':
            # INVARIANT: Cannot buy NO if we hold YES
            if inventories['YES'] > 0: return None
            
            orders.append({'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 'price': no_ask, 'expiry': current_time + timedelta(seconds=15), 'source': 'MM', 'time': current_time})
            
        return orders

class MicroScalper(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5, threshold=1.0, profit_target=1):
        super().__init__(name, risk_pct)
        self.threshold = threshold
        self.profit_target = profit_target
        self.last_mids = {}
        
    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        yes_ask = market_state.get('yes_ask')
        cur_bid = market_state.get('yes_bid', (100 - market_state.get('no_ask')) if not pd.isna(market_state.get('no_ask')) else np.nan)
        
        if pd.isna(yes_ask) or pd.isna(cur_bid): return None
        mid = (cur_bid + yes_ask) / 2.0
        
        # Fair Price Snapshot
        last_mid = self.last_mids.get(ticker)
        self.last_mids[ticker] = mid
        
        # Entry Logic - NO EXITS
        if last_mid is None: return None
        
        # Persistence: If we are already resting, don't re-enter
        if active_orders: return None
        
        delta = mid - last_mid
        
        spread = yes_ask - cur_bid
        if spread > 10 or spread <= 1: return None 
        
        if delta >= self.threshold:
            # Spike UP -> Expect Reversion Down -> BUY NO
            return [{'action': 'BUY_NO', 'ticker': ticker, 'qty': 10, 'price': int(100 - yes_ask + 1), 'expiry': current_time + timedelta(seconds=60), 'source': 'Scalper', 'time': current_time}]
        elif delta <= -self.threshold:
            # Spike DOWN -> Expect Reversion Up -> BUY YES
            return [{'action': 'BUY_YES', 'ticker': ticker, 'qty': 10, 'price': int(cur_bid + 1), 'expiry': current_time + timedelta(seconds=60), 'source': 'Scalper', 'time': current_time}]
            
        return None

class RegimeSwitcher(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5, active_hours=None, tightness_percentile=20, **mm_kwargs):
        super().__init__(name, risk_pct)
        # Pass mm_kwargs to InventoryAwareMarketMaker
        if 'margin_cents' not in mm_kwargs: mm_kwargs['margin_cents'] = 4.0
        self.mm = InventoryAwareMarketMaker("Sub-MM", risk_pct, **mm_kwargs)
        self.scalper = MicroScalper("Sub-Scalper", risk_pct)
        self.spread_histories = defaultdict(list)
        self.active_hours = active_hours # list of ints or None
        self.tightness_percentile = tightness_percentile
        # Shadow Inventories for attribution/logic
        self.mm_inventory = defaultdict(int) 
        self.sc_inventory = defaultdict(int)
        
    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        # portfolios_inventories is dict { 'MM': {'YES': qty, 'NO': qty}, 'Scalper': {'YES': qty, 'NO': qty} }
        
        yes_ask = best_yes_ask(market_state)
        yes_bid = best_yes_bid(market_state)
        if pd.isna(yes_ask) or pd.isna(yes_bid): return None
        
        spread = yes_ask - yes_bid
        hist = self.spread_histories[ticker]
        hist.append(spread)
        if len(hist) > 500: hist.pop(0)
        
        # Relax Gating: Use configurable percentile for "tightness"
        tight_threshold = np.percentile(hist, self.tightness_percentile) if len(hist) > 100 else sum(hist)/len(hist)
        is_tight = spread <= tight_threshold
        
        h = current_time.hour
        if self.active_hours is not None:
            is_active_hour = h in self.active_hours
        else:
            is_active_hour = (not ENABLE_TIME_CONSTRAINTS) or (5 <= h <= 8) or (13 <= h <= 17) or (21 <= h <= 23)
        
        if not is_active_hour:
            self.reason = f"Outside active hours (Hour: {h})"
            return None
        
        self.reason = f"Active Hour {h}, Tightness: {spread} <= {tight_threshold:.2f} ({is_tight})"

        # Partition active orders by source
        mm_active = [o for o in active_orders if o.get('source') == 'MM']
        sc_active = [o for o in active_orders if o.get('source') == 'Scalper']
        
        # Isolated Routing
        mm_inv = portfolios_inventories.get('MM', {'YES': 0, 'NO': 0})
        
        mm_orders = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, spendable_cash, idx) if is_active_hour and is_tight else (None if not is_active_hour else [])
        scalper_orders = None 

        if mm_orders is None and scalper_orders is None: return None
        
        combined = []
        if mm_orders is not None: combined.extend(mm_orders)
        else: combined.extend(mm_active)
        
        if scalper_orders is not None: combined.extend(scalper_orders)
        else: combined.extend(sc_active)
        
        return combined

# --- Live Trader V5 ---
class LiveTraderV5:
    def __init__(self):
        self.strategy = RegimeSwitcher("Live RegimeSwitcher", risk_pct=0.50)
        self.file_offsets = {} # {filename: byte_offset}
        self.file_headers = {} # {filename: [columns]}
        self.last_status_time = None
        self.launch_time = datetime.now()
        
        # API State
        self.balance = 0.0
        self.portfolio_value = 0.0 # Current Mark-to-Market Value
        self.daily_start_equity = 0.0 # Snapshot at 5 AM (Cash + Invested)
        self.last_reset_date = None
        self.spent_today = 0.0 # Track daily spend to enforce budget cap
        self.positions = {} # {ticker: {'qty': qty, 'cost': cost}}
        
        # Last Decision State (for dashboard)
        self.last_decision = {}

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
                "portfolio_value": self.portfolio_value,
                "pnl_today": self.get_total_equity() - self.daily_start_equity,
                "trades_today": len(self.positions),
                "daily_budget": budget,
                "daily_start_equity": self.daily_start_equity,
                "current_exposure": self.portfolio_value, # Approx
                "spent_today": self.spent_today,
                "spent_pct": spent_pct,
                "positions": self.positions,
                "target_date": "Dec 17+",
                "last_decision": self.last_decision
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
                    
                    # Determine side (simplified)
                    # Kalshi API returns position: positive for YES, negative for NO?
                    # Actually, 'position' is just count. 'side' might be needed.
                    # Assuming YES for now as per previous logic, but we need to be careful.
                    # For now, just tracking Qty and Cost.
                    
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
            # Check if file grew
            if not os.path.exists(log_file): return
            current_size = os.path.getsize(log_file)
            last_offset = self.file_offsets.get(log_file, 0)
            
            if current_size == last_offset:
                return
            
            # If new file or file truncated (size < offset), reset
            if last_offset == 0 or current_size < last_offset:
                print(f"Tracking new/reset log file: {os.path.basename(log_file)}")
                # Full Read
                df = pd.read_csv(log_file, on_bad_lines='skip')
                self.file_offsets[log_file] = current_size
                # Save columns for later partial reads
                self.file_headers[log_file] = df.columns.tolist()
                
                # Process all
                for index, row in df.iterrows():
                    self.on_tick(row)
            else:
                # Partial Read
                with open(log_file, 'r') as f:
                    f.seek(last_offset)
                    try:
                        # Read new data as CSV
                        # We assume the file header is known from the initial read
                        if log_file in self.file_headers:
                            new_df = pd.read_csv(f, names=self.file_headers[log_file], header=None, on_bad_lines='skip')
                            
                            # Update offset
                            self.file_offsets[log_file] = f.tell()
                            
                            for index, row in new_df.iterrows():
                                self.on_tick(row)
                        else:
                            # Fallback if we somehow missed the header (shouldn't happen if logic holds)
                            # Just read full file to be safe and set header
                            df = pd.read_csv(log_file, on_bad_lines='skip')
                            self.file_offsets[log_file] = current_size
                            self.file_headers[log_file] = df.columns.tolist()
                            # We might re-process some rows here if we fall back, but it's safer than crashing
                            
                    except pd.errors.EmptyDataError:
                        pass # No new data found
                        
        except Exception as e:
            print(f"Error reading log {os.path.basename(log_file)}: {e}")

    def on_tick(self, row):
        ticker = row['market_ticker']
        # Parse timestamp
        try:
            current_time = pd.to_datetime(row['timestamp'])
        except:
            return

        # Map row to market_state
        market_state = {
            'yes_ask': row.get('implied_yes_ask', np.nan),
            'yes_bid': row.get('implied_yes_bid', np.nan),
            'no_ask': row.get('implied_no_ask', np.nan),
            'no_bid': row.get('implied_no_bid', np.nan)
        }
        
        if pd.isna(market_state['yes_ask']) and pd.isna(market_state['no_ask']): return
        
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
        
        # Construct Inventory for Strategy
        # LiveTrader doesn't distinguish source, so we give MM full credit.
        current_qty = 0
        if ticker in self.positions:
            current_qty = self.positions[ticker]['qty']
            
        # Assuming we hold YES for now (simplification)
        # Ideally we check side, but positions dict is simple.
        # Let's assume YES for inventory check.
        inventories = {
            'MM': {'YES': current_qty, 'NO': 0},
            'Scalper': {'YES': 0, 'NO': 0}
        }
        
        active_orders = [] # We don't track active limit orders in this version (Assume Immediate Fill)
        
        # Strategy Logic
        orders = self.strategy.on_market_update(ticker, market_state, current_time, inventories, active_orders, self.balance)
        
        # Update Dashboard State
        self.last_decision = {
            'ticker': ticker,
            'mid': (market_state['yes_ask'] + market_state['yes_bid'])/2 if not pd.isna(market_state['yes_ask']) and not pd.isna(market_state['yes_bid']) else 0,
            'spread': market_state['yes_ask'] - market_state['yes_bid'] if not pd.isna(market_state['yes_ask']) and not pd.isna(market_state['yes_bid']) else 0,
            'reason': self.strategy.reason,
            'timestamp': current_time.strftime('%H:%M:%S')
        }
        
        if orders:
            for order in orders:
                # Only trade if data is FRESH (arrived after launch)
                if current_time >= self.launch_time:
                    self.execute_trade(order, current_time)

    def execute_trade(self, order, timestamp):
        action = order['action']
        ticker = order['ticker']
        qty = order['qty']
        price = order['price'] # Limit Price
        
        # 1. Check Existing Position (Prevent Double-Buy)
        if ticker in self.positions:
            return # Already hold this ticker
            
        # 2. Determine Side
        if action == "BUY_YES":
            side = 'yes'
        elif action == "BUY_NO":
            side = 'no'
        else: return
        
        # 3. Budget Check (Based on Daily Start Equity)
        # Risk Management: Spend risk_pct of DAILY START EQUITY
        budget = self.daily_start_equity * self.strategy.risk_pct
        
        # DEDUCT SPENT TODAY
        available_budget = budget - self.spent_today
        if available_budget <= 0:
            return

        cost_per_share = price / 100.0
        
        if cost_per_share <= 0: return
        
        # Cap Qty by Budget
        max_qty_budget = int(available_budget // cost_per_share)
        qty = min(qty, max_qty_budget)
        
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
        print(f"Reason: {self.strategy.reason}")
        print(f"Daily Budget Base (Equity): ${self.daily_start_equity:.2f}")
        print(f"Spent Today: ${self.spent_today:.2f} / ${self.daily_start_equity * self.strategy.risk_pct:.2f}")
        print(f"Real Balance: ${self.balance:.2f}")
        print(f"Total Equity: ${self.get_total_equity():.2f}")
        print(f"Active Positions: {len(self.positions)}")
        for ticker, data in self.positions.items():
            print(f"  - {ticker}: {data['qty']} contracts (Cost: ${data['cost']:.2f})")
        print("---------------------------------------------------\n")

    def run(self):
        print("=== Live Trader V5 (Regime Switcher / Aggressive Limits) ===")
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
