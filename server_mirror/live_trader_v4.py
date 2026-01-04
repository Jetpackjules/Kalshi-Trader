import asyncio
import base64
import json
import time
import requests
import csv
import os
import uuid
import glob
import re
import pandas as pd
import numpy as np
import math
from collections import defaultdict
from datetime import datetime, timedelta, date
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
import sys
import traceback

def _log_unhandled(exc_type, exc, tb):
    with open("crash.log", "a") as f:
        f.write("\n\n=== UNHANDLED EXCEPTION ===\n")
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        f.write("".join(traceback.format_exception(exc_type, exc, tb)))
sys.excepthook = _log_unhandled

# --- Configuration ---
LOG_DIR = "market_logs"
TRADES_LOG_FILE = "trades.csv"
ORDERS_LOG_FILE = "trades.csv" # Point to trades.csv for dashboard compatibility
MIN_REQUOTE_INTERVAL = 2.0 # Seconds between refreshing orders for a ticker
ORDER_CACHE_TTL = 1.0 # Seconds to trust cached open orders
RETRYABLE_HTTP = {502, 503, 504}

# API Config
KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
API_URL = "https://api.elections.kalshi.com"

# Path Setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_KEY_NAME = "kalshi_prod_private_key.pem"
_REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


def _pick_private_key_path() -> str:
    env_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    same_dir = os.path.join(SCRIPT_DIR, _DEFAULT_KEY_NAME)
    if os.path.exists(same_dir):
        return same_dir

    keys_dir = os.path.join(_REPO_ROOT, "keys", _DEFAULT_KEY_NAME)
    if os.path.exists(keys_dir):
        return keys_dir

    # Fall back to the original expected location for a clearer error message.
    return same_dir


PRIVATE_KEY_PATH = _pick_private_key_path()

# --- Helper Functions (From Backtest) ---
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

def sanitize_price(p):
    if pd.isna(p): return p
    if p > 95: return 100.0
    if p < 5: return 0.0
    return p

# --- Strategy Classes (From Backtest) ---

class ComplexStrategy:
    def __init__(self, name, risk_pct=0.5):
        self.name = name
        self.risk_pct = risk_pct
        self.reason = "Initializing..."
        
    def on_market_update(self, ticker, market_state, current_time, inventory, active_orders, spendable_cash, idx=0):
        return None

class InventoryAwareMarketMaker(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5, max_inventory=500, inventory_penalty=0.1, max_offset=2, alpha=0.1):
        super().__init__(name, risk_pct)
        self.max_inventory = max_inventory
        self.inventory_penalty = inventory_penalty
        self.max_offset = max_offset
        self.alpha = alpha
        
        self.fair_prices = {} 
        self.last_quote_time = {} 
        self.last_mid_snapshot = {} 

    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        yes_ask = best_yes_ask(market_state)
        no_ask = market_state.get('no_ask', np.nan)
        yes_bid = best_yes_bid(market_state)
        
        debug = {"fair": 0, "edge": 0, "status": "Initializing"}

        if pd.isna(yes_ask) or pd.isna(yes_bid):
            debug["status"] = "Missing price data"
            return None, debug

        mid = (yes_bid + yes_ask) / 2.0
        self.last_mid_snapshot[ticker] = mid
        self.last_quote_time[ticker] = current_time

        hist = self.fair_prices.get(ticker, [])
        hist.append(mid)
        if len(hist) > 20: hist.pop(0)
        self.fair_prices[ticker] = hist
        
        if len(hist) < 20: 
            debug["status"] = f"Warmup ({len(hist)}/20)"
            return None, debug
        
        mean_price = np.mean(hist)
        fair_prob = mean_price / 100.0
        debug["fair"] = round(mean_price, 2)
        
        exec_yes_prob_for_yes = yes_ask / 100.0
        exec_yes_prob_for_no = np.nan
        if not pd.isna(no_ask):
             exec_yes_prob_for_no = 1.0 - (no_ask / 100.0) 
        
        edge = 0
        action = None
        price_to_pay = 0
        
        edge_yes = fair_prob - exec_yes_prob_for_yes
        edge_no = np.nan
        if not pd.isna(no_ask):
            edge_no = (1.0 - fair_prob) - (no_ask / 100.0)
        
        if edge_yes > 0:
            edge = edge_yes
            action = 'BUY_YES'
            price_to_pay = yes_ask
        elif not pd.isna(edge_no) and edge_no > 0:
            edge = edge_no
            action = 'BUY_NO'
            price_to_pay = no_ask
            
        if action is None: 
            debug["status"] = f"No Edge (Fair {mean_price:.1f} vs YAsk {yes_ask:.1f}/NAsk {no_ask:.1f})"
            return None, debug
        
        debug["edge"] = round(edge * 100, 2)
        
        dummy_qty = 10
        fee_est = calculate_convex_fee(price_to_pay, dummy_qty) / dummy_qty
        fee_cents = fee_est * 100
        
        required_edge_cents = fee_cents + 0.5
        
        if (edge * 100) < required_edge_cents: 
            debug["status"] = f"Edge {edge*100:.2f}c < Req {required_edge_cents:.2f}c"
            return None, debug
        
        edge_cents = edge * 100.0
        p = price_to_pay / 100.0
        fee_per_contract = 0.07 * p * (1 - p)
        fee_cents = fee_per_contract * 100.0

        edge_after_fee = edge_cents - fee_cents - 0.5
        if edge_after_fee <= 0:
            debug["status"] = f"Edge after fee {edge_after_fee:.2f}c <= 0"
            return None, debug

        scale = min(1.0, edge_after_fee / 4.0)

        max_notional = spendable_cash * 0.25
        max_loss = spendable_cash * 0.06

        price_unit = price_to_pay / 100.0
        cost_unit = price_unit + fee_per_contract

        qty_by_notional = int(max_notional / cost_unit) if cost_unit > 0 else 0
        qty_by_loss = int(max_loss / cost_unit) if cost_unit > 0 else 0

        base_qty = min(qty_by_notional, qty_by_loss)
        if base_qty <= 0:
            debug["status"] = f"Size 0 (Cash ${spendable_cash:.2f})"
            return None, debug

        # INVENTORY CHECK (Includes Pending)
        current_inv = inventories['YES'] if action == 'BUY_YES' else inventories['NO']
        room = self.max_inventory - current_inv
        if room <= 0:
            debug["status"] = f"Inventory Full ({current_inv})"
            return None, debug

        inv_penalty = 1.0 / (1.0 + current_inv / 200.0)

        qty = int(base_qty * scale * inv_penalty)
        qty = max(1, min(qty, room))
        
        fee_real = calculate_convex_fee(price_to_pay, qty)
        fee_cents_real = (fee_real / qty) * 100.0
        
        edge_after_fee_real = edge_cents - fee_cents_real - 0.5
        if edge_after_fee_real <= 0:
            debug["status"] = f"Real edge after fee {edge_after_fee_real:.2f}c <= 0"
            return None, debug
        
        orders = []
        
        # WALL CLOCK EXPIRY
        expiry = datetime.now() + timedelta(seconds=15)
        
        if action == 'BUY_YES':
            if inventories['NO'] > 0: 
                debug["status"] = "Opposite Inventory (NO)"
                return None, debug
            orders.append({'action': 'BUY_YES', 'ticker': ticker, 'qty': qty, 'price': yes_ask, 'expiry': expiry, 'source': 'MM', 'time': current_time})
        
        elif action == 'BUY_NO':
            if inventories['YES'] > 0: 
                debug["status"] = "Opposite Inventory (YES)"
                return None, debug
            orders.append({'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 'price': no_ask, 'expiry': expiry, 'source': 'MM', 'time': current_time})
            
        debug["status"] = f"SIGNAL {action} {qty} @ {price_to_pay}"
        return orders, debug

class RegimeSwitcher(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5):
        super().__init__(name, risk_pct)
        self.mm = InventoryAwareMarketMaker("Sub-MM", risk_pct)
        self.spread_histories = defaultdict(list)
        self.last_decision = {} # {ticker, mid, spread, reason, timestamp}
        
    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        yes_ask = best_yes_ask(market_state)
        yes_bid = best_yes_bid(market_state)
        
        # Default decision state
        decision = {
            "ticker": ticker,
            "mid": 0.0,
            "spread": 0.0,
            "reason": "Waiting for data...",
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }

        if pd.isna(yes_ask) or pd.isna(yes_bid): 
            decision["reason"] = "Missing price data"
            self.last_decision = decision
            return None
        
        spread = yes_ask - yes_bid
        mid = (yes_ask + yes_bid) / 2.0
        
        decision["mid"] = round(mid, 1)
        decision["spread"] = round(spread, 1)
        
        hist = self.spread_histories[ticker]
        hist.append(spread)
        if len(hist) > 500: hist.pop(0)
        
        tight_threshold = np.percentile(hist, 50) if len(hist) > 100 else sum(hist)/len(hist)
        is_tight = spread <= tight_threshold
        
        h = current_time.hour
        is_active_hour = (5 <= h <= 8) or (13 <= h <= 17) or (21 <= h <= 23)
        
        if not is_active_hour:
            decision["reason"] = f"Outside active hours (Hour: {h})"
        elif not is_tight:
            decision["reason"] = f"Spread {spread:.1f}c > Threshold {tight_threshold:.1f}c"
        else:
            decision["reason"] = "Market Active & Tight"
            
        mm_active = [o for o in active_orders if o.get('source') == 'MM']
        
        mm_inv = portfolios_inventories.get('MM', {'YES': 0, 'NO': 0})
        
        mm_orders = None
        mm_debug = None
        if is_active_hour and is_tight:
            mm_orders, mm_debug = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, spendable_cash, idx)
            if mm_debug:
                decision["reason"] = mm_debug["status"]
                decision["fair"] = mm_debug["fair"]
                decision["edge"] = mm_debug["edge"]
        elif not is_active_hour:
            mm_orders = None
        else:
            mm_orders = []
            
        self.last_decision = decision
        
        if mm_orders is None: return None
        
        combined = []
        if mm_orders is not None: combined.extend(mm_orders)
        else: combined.extend(mm_active)
        
        return combined

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

# --- Live Trader V4 ---
class LiveTraderV4:
    def __init__(self):
        self.strategy = RegimeSwitcher("Live RegimeSwitcher", risk_pct=0.5)
        self.file_offsets = {} 
        self.file_headers = {}
        # Order Management
        self.order_cache = {} # {ticker: {'orders': [], 'timestamp': ts}}
        self.open_orders_snapshot = [] # Global snapshot
        self.open_orders_snapshot_ts = 0
        self.last_requote_time = {} # {ticker: ts}
        
        # State Tracking
        self.daily_start_equity = 0.0
        self.last_reset_date = ""
        self.balance = 0.0
        self.portfolio_value = 0.0
        self.positions = {}
        
        # Shadow State (for high-frequency tracking)
        self.shadow_balance = 0.0
        self.shadow_positions = defaultdict(lambda: {'yes': 0, 'no': 0})
        self.shadow_anchor_balance = 0.0
        self.shadow_spent_since_sync = 0.0
        self.last_status_time = None
        
        # Load Key Once
        try:
            with open(PRIVATE_KEY_PATH, 'rb') as f:
                self.private_key = serialization.load_pem_private_key(f.read(), password=None)
        except Exception as e:
            print(f"CRITICAL: Failed to load private key from {PRIVATE_KEY_PATH}: {e}")
            exit(1)

    def check_control_flag(self):
        try:
            if os.path.exists("trading_enabled.txt"):
                with open("trading_enabled.txt", "r") as f:
                    return f.read().strip().lower() == "true"
            else:
                with open("trading_enabled.txt", "w") as f:
                    f.write("true")
                return True
        except: return True

    def calculate_trades_today_count(self):
        # Count lines in orders.csv for now, or 0
        if not os.path.exists(ORDERS_LOG_FILE): return 0
        count = 0
        today_str = datetime.now().strftime('%Y-%m-%d')
        try:
            with open(ORDERS_LOG_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['timestamp'].startswith(today_str):
                        count += 1
        except: pass
        return count

    def get_total_exposure(self):
        # 1. Positions Cost
        pos_cost = sum(p['cost'] for p in self.positions.values())
        
        # 2. Open Orders Cost (Merged Snapshot + Cache)
        orders_by_ticker = defaultdict(list)
        
        # Start with snapshot
        for o in self.open_orders_snapshot:
            if isinstance(o, tuple): continue # Skip malformed data
            if not isinstance(o, dict): continue
            orders_by_ticker[o.get('ticker')].append(o)
            
        # Overlay cache if newer
        for ticker, cache in self.order_cache.items():
            cache_ts, cache_orders = cache
            if cache_ts > self.open_orders_snapshot_ts:
                orders_by_ticker[ticker] = cache_orders
        
        order_cost = 0.0
        for ticker, orders in orders_by_ticker.items():
            for o in orders:
                status = (o.get("status") or "").lower()
                remaining = o.get("remaining_count", 0)
                if remaining <= 0: continue
                if status in ("executed", "cancelled", "canceled", "expired", "rejected"): continue
                
                side = (o.get('side') or 'yes').lower()
                price = o.get('yes_price') if side == 'yes' else o.get('no_price')
                
                if price is None or pd.isna(price):
                    continue

                fee = calculate_convex_fee(price, remaining)
                cost = (remaining * (price / 100.0)) + fee
                order_cost += cost
                
        return pos_cost + order_cost + self.shadow_spent_since_sync

    def update_status_file(self, status="RUNNING"):
        try:
            budget = self.daily_start_equity * self.strategy.risk_pct
            current_exposure = self.get_total_exposure()
            
            spent_pct = (current_exposure / budget * 100) if budget > 0 else 0.0
            current_equity = self.get_total_equity()
            pnl_today = current_equity - self.daily_start_equity
            trades_count = self.calculate_trades_today_count()
            
            data = {
                "status": status,
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "strategy": self.strategy.name,
                "equity": current_equity,
                "cash": self.balance,
                "portfolio_value": self.portfolio_value,
                "pnl_today": pnl_today,
                "trades_today": trades_count,
                "daily_budget": budget,
                "daily_start_equity": self.daily_start_equity,
                "current_exposure": current_exposure,
                "spent_today": current_exposure, # Alias for dashboard compatibility
                "spent_pct": spent_pct,
                "positions": self.positions,
                "target_date": "Dec 17+",
                "last_decision": getattr(self.strategy, "last_decision", {})
            }
            with open("trader_status.json", "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error updating status file: {e}")

    def get_total_equity(self):
        return self.balance + self.portfolio_value

    def make_api_request(self, method, path, payload=None):
        url = f"{API_URL}{path}"
        last_err = None
        
        for attempt in range(3):
            headers = create_headers(self.private_key, method, path)
            
            try:
                if method == "GET":
                    resp = requests.get(url, headers=headers, timeout=10)
                elif method == "POST":
                    resp = requests.post(url, headers=headers, json=payload, timeout=10)
                elif method == "DELETE":
                    resp = requests.delete(url, headers=headers, timeout=10)
                else:
                    print(f"API Request Error: Unsupported method {method}", flush=True)
                    return None

                # Retry on 429
                if resp.status_code == 429:
                    print(f"⚠️ API Rate Limit (429) - Attempt {attempt+1}. Backing off...", flush=True)
                    time.sleep(1.0 + 0.2 * attempt)
                    continue

                # Retry on transient 5xx
                if resp.status_code in RETRYABLE_HTTP:
                    print(f"⚠️ API Server Error ({resp.status_code}) - Attempt {attempt+1}. Backing off...", flush=True)
                    time.sleep(0.5 * (2 ** attempt) + 0.1 * attempt)
                    continue
                
                return resp

            except Exception as e:
                print(f"⚠️ API Network Error ({method} {path}) - Attempt {attempt+1}: {repr(e)}", flush=True)
                time.sleep(0.5 * (2 ** attempt) + 0.1 * attempt)
                last_err = e
        
        print(f"❌ API Request FAILED after 3 attempts ({method} {path}): {repr(last_err)}", flush=True)
        return None

    def refresh_open_orders_snapshot(self):
        resp = self.make_api_request("GET", "/trade-api/v2/portfolio/orders")
        if resp and resp.status_code == 200:
            self.open_orders_snapshot = resp.json().get("orders", [])
            self.open_orders_snapshot_ts = time.time()
            # print(f"DEBUG: Refreshed open orders snapshot. Count: {len(self.open_orders_snapshot)}")
        else:
            print(f"OPEN_ORDERS_SNAPSHOT_FAIL {resp.status_code if resp else None} {resp.text if resp else ''}", flush=True)

    def sync_api_state(self, force_reset_daily=False):
        try:
            # Balance
            resp = self.make_api_request("GET", "/trade-api/v2/portfolio/balance")
            if resp and resp.status_code == 200:
                data = resp.json()
                self.balance = data.get("balance", 0) / 100.0
                self.portfolio_value = data.get("portfolio_value", 0) / 100.0
            
            # Positions
            resp = self.make_api_request("GET", "/trade-api/v2/portfolio/positions")
            if resp and resp.status_code == 200:
                raw_positions = resp.json().get("market_positions", [])
                self.positions = {}
                for p in raw_positions:
                    raw_qty = p.get('position', 0)
                    qty = abs(raw_qty)
                    if qty > 0:
                        exposure = p.get('market_exposure', 0)
                        fees = p.get('fees_paid', 0)
                        cost = (exposure + fees) / 100.0
                        
                        ticker = p['ticker']
                        if ticker not in self.positions:
                            self.positions[ticker] = {'yes': 0, 'no': 0, 'cost': 0}
                        
                        if raw_qty > 0:
                            self.positions[ticker]['yes'] = qty
                        else:
                            self.positions[ticker]['no'] = qty
                            
                        self.positions[ticker]['cost'] = cost

            # Daily Reset
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            current_equity = self.get_total_equity()
            
            if self.daily_start_equity == 0.0 or force_reset_daily:
                self.daily_start_equity = current_equity
                self.last_reset_date = today_str
                print(f"  [BUDGET] Daily Start Equity: ${self.daily_start_equity:.2f}")
                
                # --- DAILY SNAPSHOT ---
                try:
                    snap_dir = os.path.expanduser("~/snapshots")
                    if not os.path.exists(snap_dir):
                        os.makedirs(snap_dir)
                        
                    snap_file = os.path.join(snap_dir, f"snapshot_{today_str}.json")
                    
                    # Create comprehensive snapshot
                    snapshot_data = {
                        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "date": today_str,
                        "daily_start_equity": self.daily_start_equity,
                        "balance": self.balance,
                        "portfolio_value": self.portfolio_value,
                        "positions": self.positions,
                        "strategy_config": {
                            "name": self.strategy.name,
                            "risk_pct": self.strategy.risk_pct
                        }
                    }
                    
                    with open(snap_file, "w") as f:
                        json.dump(snapshot_data, f, indent=2)
                    print(f"  [SNAPSHOT] Saved daily snapshot to {snap_file}")
                    
                except Exception as e:
                    print(f"  [SNAPSHOT] Error saving snapshot: {e}")
            
            # Refresh Shadows
            self.shadow_balance = self.balance
            self.shadow_positions.clear()
            for tkr, p in self.positions.items():
                self.shadow_positions[tkr]["yes"] = p["yes"]
                self.shadow_positions[tkr]["no"]  = p["no"]
            
            self.shadow_anchor_balance = self.shadow_balance
            self.shadow_spent_since_sync = 0.0
                    
        except Exception as e:
            print(f"Error syncing API state: {e}")

    def get_open_orders_cached(self, ticker):
        now = time.time()
        if ticker in self.order_cache:
            cached_time, orders = self.order_cache[ticker]
            if now - cached_time < ORDER_CACHE_TTL:
                return orders
        
        resp = self.make_api_request("GET", f"/trade-api/v2/portfolio/orders?ticker={ticker}")
        if resp is None:
            print(f"OPEN_ORDERS_FAIL {ticker} resp=None", flush=True)
            return None # UNKNOWN, not empty list
            
        if resp.status_code != 200:
            print(f"OPEN_ORDERS_FAIL {ticker} {resp.status_code}: {resp.text}", flush=True)
            # If it's a transient server error and we have *any* cached data, use stale cache instead of None
            if resp.status_code in RETRYABLE_HTTP and ticker in self.order_cache:
                return self.order_cache[ticker][1]
            return None # UNKNOWN

        try:
            data = resp.json()
            orders = data.get('orders', [])
            self.order_cache[ticker] = (now, orders)
            return orders
        except Exception:
            return None

    def cancel_order(self, order_id):
        self.make_api_request("DELETE", f"/trade-api/v2/portfolio/orders/{order_id}")

    def place_real_order(self, ticker, qty, price, side, expiry_ts):
        # Force integers for Kalshi API
        price = int(round(price))
        qty = int(qty)

        # Client Order ID: MM_{expiry}_{uuid}
        short_uuid = str(uuid.uuid4())[:8]
        client_oid = f"MM_{int(expiry_ts.timestamp())}_{short_uuid}"
        
        payload = {
            "action": "buy",
            "count": qty,
            "side": side,
            "ticker": ticker,
            "type": "limit",
            "yes_price" if side == 'yes' else "no_price": price,
            "client_order_id": client_oid
        }
        
        resp = self.make_api_request("POST", "/trade-api/v2/portfolio/orders", payload)
        
        if resp is None:
            print(f"❌ FAIL: No response placing order (ticker={ticker} side={side} qty={qty} price={price})", flush=True)
            return False, 0.0, 0, "no_response"

        if resp.status_code == 201:
            data = resp.json().get('order', {})
            status = data.get('status', 'unknown')
            filled = data.get('filled_count', 0)
            
            print(f"✅ ORDER: {ticker} {side.upper()} {qty} @ {price} | Status: {status} | Filled: {filled}/{qty}", flush=True)
            
            # If partial fill or resting, explicit log
            if filled < qty:
                 print(f"⚠️ PARTIAL/RESTING: Requested {qty}, Filled {filled}. Reason: Liquidity at Price.", flush=True)
                 
            return True, calculate_convex_fee(price, qty), filled, status

        print(f"❌ FAIL {resp.status_code}: {resp.text} payload={payload}", flush=True)
        return False, 0.0, 0, "error"

    def fetch_new_ticks(self, log_file):
        new_rows = []
        try:
            if not os.path.exists(log_file): return []
            
            with open(log_file, 'r') as f:
                # If new file, read header to get fieldnames
                if log_file not in self.file_headers:
                    header_line = f.readline().strip()
                    self.file_headers[log_file] = header_line.split(',')
                    
                    # Optimization: Seek to end to skip processing entire history on startup
                    f.seek(0, os.SEEK_END)
                    self.file_offsets[log_file] = f.tell()
                    return []
                
                f.seek(self.file_offsets[log_file])
                
                # Use DictReader with known headers
                reader = csv.DictReader(f, fieldnames=self.file_headers[log_file])
                
                for row in reader:
                    new_rows.append(row)
                
                self.file_offsets[log_file] = f.tell()

        except Exception as e:
            print(f"Error reading log {log_file}: {e}", flush=True)
            pass
            
        return new_rows

    def process_new_data(self, log_file):
        # LEGACY: Kept for compatibility if needed, but run() will use fetch_new_ticks
        rows = self.fetch_new_ticks(log_file)
        for row in rows:
            self.on_tick(row)

    def on_tick(self, row):
        ticker = row['market_ticker']
        try:
            current_time = pd.to_datetime(row['timestamp'])
        except: return

        # Date Filter: >= Today (Timezone consistent with data stream)
        try:
            match = re.search(r'-(\d{2}[A-Z]{3}\d{2})', ticker)
            if match:
                mkt_date = datetime.strptime(match.group(1), "%y%b%d").date()
                if mkt_date < current_time.date(): return
        except: return

        # Parse prices (Force integers for consistency, handle NaNs safely)
        try:
            ya_f = float(row.get('implied_yes_ask', 'nan'))
            na_f = float(row.get('implied_no_ask', 'nan'))
            yb_f = float(row.get('best_yes_bid', 'nan'))
            nb_f = float(row.get('best_no_bid', 'nan'))

            if pd.isna(ya_f) and pd.isna(na_f):
                return

            yes_ask = int(round(ya_f)) if not pd.isna(ya_f) else np.nan
            no_ask  = int(round(na_f)) if not pd.isna(na_f) else np.nan
            yes_bid = int(round(yb_f)) if not pd.isna(yb_f) else np.nan
            no_bid  = int(round(nb_f)) if not pd.isna(nb_f) else np.nan

            # print(f"TICK {ticker} {current_time} ya={yes_ask} yb={yes_bid} na={no_ask}", flush=True)
        except Exception as e:
            print(f"PARSE_FAIL {ticker}: {repr(e)} row={row}", flush=True)
            return
        
        if pd.isna(yes_ask) and pd.isna(no_ask): return
        
        market_state = {'yes_ask': yes_ask, 'no_ask': no_ask, 'yes_bid': yes_bid, 'no_bid': no_bid}
        
        # --- 1. Fetch & Reconcile Open Orders ---
        open_orders = self.get_open_orders_cached(ticker)
        
        if open_orders is None:
            print(f"SKIP_TICK {ticker} open_orders=UNKNOWN", flush=True)
            return
        
        # Clean up expired orders
        active_orders_for_strat = []
        pending_yes = 0
        pending_no = 0
        
        for o in open_orders:
            oid = o.get('order_id')
            client_oid = o.get('client_order_id', '')
            status = (o.get("status") or "").lower()
            remaining = o.get("remaining_count", 0)
            
            # Filter inactive
            if remaining <= 0: continue
            if status in ("executed", "cancelled", "canceled", "expired", "rejected"): continue

            # Check Expiry
            expired = False
            if client_oid.startswith("MM_"):
                try:
                    exp_ts = int(client_oid.split('_')[1])
                    if time.time() > exp_ts:
                        self.cancel_order(oid)
                        expired = True
                        # Invalidate cache
                        if ticker in self.order_cache: del self.order_cache[ticker]
                except: pass
            
            if expired: continue
            
            # Map to Strategy Format
            side = (o.get('side') or 'yes').lower()
            price = o.get('yes_price') if side == 'yes' else o.get('no_price')
            
            if price is None or pd.isna(price):
                continue

            if remaining > 0:
                if side == 'yes': pending_yes += remaining
                else: pending_no += remaining
                
                active_orders_for_strat.append({
                    'action': 'BUY_YES' if side == 'yes' else 'BUY_NO',
                    'ticker': ticker,
                    'qty': remaining,
                    'price': price,
                    'source': 'MM',
                    'id': oid
                })

        print(f"OPEN_ORDERS {ticker} fetched={len(open_orders)} active_for_strat={len(active_orders_for_strat)}", flush=True)

        # --- 2. Build Inventory (Pos + Pending) ---
        pos_yes = self.shadow_positions[ticker]["yes"]
        pos_no  = self.shadow_positions[ticker]["no"]
        
        mm_inv = {
            'YES': pos_yes + pending_yes,
            'NO': pos_no + pending_no
        }
        portfolios_inventories = {'MM': mm_inv}
        
        # --- 3. Rate Limit Strategy ---
        last_req = self.last_requote_time.get(ticker, 0)
        if (time.time() - last_req) < MIN_REQUOTE_INTERVAL:
            return # Skip strategy to avoid churn
        
        # --- 4. Call Strategy ---
        desired_orders = self.strategy.on_market_update(ticker, market_state, current_time, portfolios_inventories, active_orders_for_strat, self.shadow_balance)
        
        reason = getattr(self.strategy, "last_decision", {}).get("reason", "Unknown")
        if desired_orders is None:
            if "Outside active hours" not in reason:
                print(f"NO_SIGNAL {ticker} | {reason}", flush=True)
            return # Persistence
        else:
            print(f"SIGNAL {ticker} {len(desired_orders)} | {reason}", flush=True)
        
        self.last_requote_time[ticker] = time.time()
        
        # --- 5. Reconcile ---
        # Match desired vs active
        kept_ids = set()
        unsatisfied = []
        
        for desired in desired_orders:
            matched = False
            for existing in active_orders_for_strat:
                if existing['id'] in kept_ids: continue
                
                # Tolerance: Match Side & Price. Require existing qty >= desired qty.
                if (existing['action'] == desired['action'] and 
                    existing['price'] == desired['price'] and
                    existing['qty'] >= desired['qty']):
                    
                    kept_ids.add(existing['id'])
                    matched = True
                    break
            if not matched:
                unsatisfied.append(desired)
        
        if len(unsatisfied) == 0:
            print(f"KEEP {ticker} desired={len(desired_orders)} active={len(active_orders_for_strat)} (nothing to place)", flush=True)
        else:
            print(f"NEW {ticker} unsatisfied={len(unsatisfied)} (will place)", flush=True)

        # Cancel Unwanted
        cancelled_any = False
        for existing in active_orders_for_strat:
            if existing['id'] not in kept_ids:
                self.cancel_order(existing['id'])
                cancelled_any = True
        
        if cancelled_any:
            if ticker in self.order_cache: del self.order_cache[ticker]

        # Place New
        for order in unsatisfied:
            self.execute_order(order, current_time)

    def execute_order(self, order, timestamp):
        action = order['action']
        ticker = order['ticker']
        price = order['price']
        qty = order['qty']
        expiry = order['expiry']
        
        side = 'yes' if action == 'BUY_YES' else 'no'
        
        # Budget Check (Exposure Based)
        budget = self.daily_start_equity * self.strategy.risk_pct
        current_exposure = self.get_total_exposure()
        
        fee = calculate_convex_fee(price, qty)
        cost_per_share = price / 100.0
        total_cost = (qty * cost_per_share) + fee
        
        if (current_exposure + total_cost) > budget:
            # Scale down to fit budget
            available = budget - current_exposure
            if available > 0 and total_cost > 0:
                ratio = available / total_cost
                qty = int(qty * ratio)
                fee = calculate_convex_fee(price, qty)
                total_cost = (qty * cost_per_share) + fee
            else:
                qty = 0
        
        if qty <= 0:
            print(f"SKIP {ticker} budget-fit -> qty=0 (budget={budget:.2f} exposure={current_exposure:.2f})", flush=True)
            return
        
        # Balance Check (Conservative)
        effective_cash = min(self.balance, self.shadow_balance)
        if effective_cash < total_cost:
            if total_cost > 0:
                ratio = effective_cash / total_cost
                qty = int(qty * ratio)
                fee = calculate_convex_fee(price, qty)
                total_cost = (qty * cost_per_share) + fee

        if qty <= 0:
            print(f"SKIP {ticker} balance-fit -> qty=0 (bal={effective_cash:.2f} need={total_cost:.2f})", flush=True)
        try:
            # Capture Wall Clock Time (Execution Time)
            exec_time = datetime.now()
            exec_time_str = exec_time.strftime("%Y-%m-%d %H:%M:%S.%f")
            
            # Calculate Latency (Lag between Data Tick and Execution)
            latency_ms = 0
            try:
                # Assuming timestamp format matches log format
                tick_dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
                latency_ms = (exec_time - tick_dt).total_seconds() * 1000.0
            except:
                pass

            file_exists = os.path.isfile(ORDERS_LOG_FILE)
            with open(ORDERS_LOG_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["timestamp", "strategy", "ticker", "action", "price", "qty", "cost", "fee", "exec_time", "latency_ms"])
                writer.writerow([timestamp, self.strategy.name, ticker, action, price, qty, cost, fee, exec_time_str, f"{latency_ms:.2f}"])
        except: pass

    def get_active_log_files(self):
        # Return list of log files to process
        log_dir = os.path.expanduser(f"~/{LOG_DIR}")
        if not os.path.exists(log_dir): return []
        files = glob.glob(os.path.join(log_dir, "*.csv"))
        return sorted(files)

    def run(self):
        try:
            print("=== Live Trader V4 (RegimeSwitcher / Robust) ===", flush=True)
            self.sync_api_state(force_reset_daily=True)
            self.update_status_file("STARTING")

            while True:
                if not self.check_control_flag():
                    self.update_status_file("PAUSED")
                    time.sleep(10)
                    continue

                self.update_status_file("RUNNING")
                now = datetime.now()
                
                if self.last_reset_date != now.strftime('%Y-%m-%d') and now.hour >= 5:
                    self.sync_api_state(force_reset_daily=True)
                
                # --- DETERMINISTIC BATCH PROCESSING ---
                # 1. Gather all new ticks from all active files
                all_new_ticks = []
                active_files = self.get_active_log_files()
                for log_file in active_files:
                    ticks = self.fetch_new_ticks(log_file)
                    all_new_ticks.extend(ticks)
                
                # 2. Sort by Timestamp (Global Chronological Order)
                # Ensure we parse timestamp correctly for sorting
                def parse_ts(row):
                    try: return pd.to_datetime(row['timestamp'])
                    except: return datetime.min
                
                if all_new_ticks:
                    all_new_ticks.sort(key=parse_ts)
                    
                    # 3. Process in Order
                    for row in all_new_ticks:
                        self.on_tick(row)
                    
                if self.last_status_time is None or (now - self.last_status_time).total_seconds() >= 60:
                    self.sync_api_state()
                    self.refresh_open_orders_snapshot()
                    self.print_status()
                    self.last_status_time = now
                    
                time.sleep(1)
        except Exception as e:
            import traceback
            print(f"CRASH: {e}", flush=True)
            print(traceback.format_exc(), flush=True)
            with open("crash.log", "a") as f:
                f.write("\n\n=== CAUGHT EXCEPTION IN RUN() ===\n")
                f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                f.write(traceback.format_exc())
            raise

    def print_status(self):
        print(f"\n--- Status @ {datetime.now().strftime('%H:%M:%S')} ---")
        print(f"Equity: ${self.get_total_equity():.2f} | Cash: ${self.balance:.2f}")
        print(f"Exposure: ${self.get_total_exposure():.2f} / ${self.daily_start_equity * self.strategy.risk_pct:.2f}")
        print(f"Positions: {len(self.positions)}")
        for t, p in self.positions.items():
            print(f"  {t}: YES={p['yes']} NO={p['no']} (Cost ${p['cost']:.2f})")
        print("---------------------------------------------------\n")

if __name__ == "__main__":
    trader = LiveTraderV4()
    trader.run()
