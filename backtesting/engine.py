import pandas as pd
import numpy as np
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.express as px
except ModuleNotFoundError:  # Allow non-plotting runs without plotly installed.
    go = None
    make_subplots = None
    px = None
import os
import glob
from datetime import datetime, timedelta
import sys
import math
import collections
import json
from collections import defaultdict
from functools import lru_cache

# --- Configuration ---
LOG_DIR_CANDIDATES = [
    os.path.join(os.getcwd(), "vm_logs", "market_logs"),
    os.path.join(os.getcwd(), "server_mirror", "market_logs"),
    os.path.join(os.getcwd(), "live_trading_system", "vm_logs", "market_logs"),
]
LOG_DIR = next((d for d in LOG_DIR_CANDIDATES if os.path.exists(d)), LOG_DIR_CANDIDATES[0])
CHARTS_DIR = "backtest_charts"
INITIAL_CAPITAL = 100.00
START_DATE = "25DEC04"
END_DATE = ""
ENABLE_TIME_CONSTRAINTS = True # Set to False to trade 24/7

if not os.path.exists(CHARTS_DIR):
    os.makedirs(CHARTS_DIR)

# --- Constants for Settlement ---
MARKET_END_HOUR = 0      # 00:00 next day
PAYOUT_HOUR = 1          # 01:00 next day


def _verbose_enabled() -> bool:
    value = os.environ.get("BT_VERBOSE", "").strip().lower()
    return value not in ("", "0", "false", "no")

@lru_cache(maxsize=None)
def parse_market_date_from_ticker(ticker: str):
    parts = ticker.strip().split('-')
    for p in parts:
        if len(p) == 7 and p[:2].isdigit():
            try:
                return datetime.strptime(p, "%y%b%d")
            except:
                pass
    return None

@lru_cache(maxsize=None)
def market_end_time_from_ticker(ticker: str):
    d = parse_market_date_from_ticker(ticker)
    if d is None:
        return None
    # Market ends at 00:00 the NEXT day (end of market-date)
    end_dt = (d + timedelta(days=1)).replace(hour=MARKET_END_HOUR, minute=0, second=0, microsecond=0)
    return end_dt

@lru_cache(maxsize=None)
def payout_time_from_ticker(ticker: str):
    d = parse_market_date_from_ticker(ticker)
    if d is None:
        return None
    pay_dt = (d + timedelta(days=1)).replace(hour=PAYOUT_HOUR, minute=0, second=0, microsecond=0)
    return pay_dt

# --- Wallet Class ---
class Wallet:
    def __init__(self, initial_capital):
        self.available_cash = initial_capital
        self.unsettled_positions = [] 
        
    def get_total_equity(self):
        unsettled_total = sum(p['amount'] for p in self.unsettled_positions)
        return self.available_cash + unsettled_total

    def check_settlements(self, current_time):
        remaining_unsettled = []
        for p in self.unsettled_positions:
            if p['settle_time'] <= current_time:
                self.available_cash += p['amount']
            else:
                remaining_unsettled.append(p)
        self.unsettled_positions = remaining_unsettled

    def spend(self, amount):
        if amount > self.available_cash + 0.0001:
            return False
        self.available_cash -= amount
        return True

    def add_cash(self, amount):
        self.available_cash += amount

    def add_unsettled(self, amount, settle_time):
        self.unsettled_positions.append({'amount': amount, 'settle_time': settle_time})

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

def settle_mid_price(last_mid: float) -> float:
    """Settle at last known mid, but snap to 100/0 if within 1%."""
    if pd.isna(last_mid):
        return np.nan
    if last_mid >= 99.0:
        return 100.0
    if last_mid <= 1.0:
        return 0.0
    return float(last_mid)

def _require_plotly():
    if go is None or make_subplots is None or px is None:
        raise ImportError("plotly is required for charting. Install plotly to generate charts.")

# --- Complex Strategy Base Class ---
class ComplexStrategy:
    def __init__(self, name, risk_pct=0.5):
        self.name = name
        self.risk_pct = risk_pct
        
    def on_market_update(self, ticker, market_state, current_time, inventory, active_orders, spendable_cash, idx=0):
        """
        Returns: 
           list of dicts: New state (Replace current active orders)
           None: Keep current orders (Persistence)
        """
        return None

# --- Implementation of Strategy 2.5 (V2 Refined) ---

class InventoryAwareMarketMaker(ComplexStrategy):
    def __init__(
        self,
        name,
        risk_pct=0.5,
        max_inventory=50,
        hmax_inventory=None,
        inventory_penalty=0.5,
        max_offset=2,
        alpha=0.1,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.05,
        max_loss_pct=0.02,
    ):
        super().__init__(name, risk_pct)
        if hmax_inventory is not None and max_inventory == 50:
            max_inventory = hmax_inventory
        self.max_inventory = max_inventory
        self.inventory_penalty = inventory_penalty
        self.max_offset = max_offset
        self.alpha = alpha
        
        # New configurable params
        self.margin_cents = margin_cents

# --- Complex Strategy Base Class ---
class ComplexStrategy:
    def __init__(self, name, risk_pct=0.5):
        self.name = name
        self.risk_pct = risk_pct
        
    def on_market_update(self, ticker, market_state, current_time, inventory, active_orders, spendable_cash, idx=0):
        """
        Returns: 
           list of dicts: New state (Replace current active orders)
           None: Keep current orders (Persistence)
        """
        return None

# --- Implementation of Strategy 2.5 (V2 Refined) ---

class InventoryAwareMarketMaker(ComplexStrategy):
    def __init__(
        self,
        name,
        risk_pct=0.5,
        max_inventory=50,
        hmax_inventory=None,
        inventory_penalty=0.5,
        max_offset=2,
        alpha=0.1,
        margin_cents=4.0,
        scaling_factor=4.0,
        max_notional_pct=0.05,
        max_loss_pct=0.02,
    ):
        super().__init__(name, risk_pct)
        if hmax_inventory is not None and max_inventory == 50:
            max_inventory = hmax_inventory
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
        self.last_debug = {} # Added for debugging

    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        # Handle UnifiedEngine passing full portfolio dict
        if "MM" in inventories:
            inventories = inventories["MM"]
        self.last_debug = {} # Reset debug
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
        
        # if len(hist) < 20: return None # Warmup
        
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
            
        if action is None:
            self.last_decision = {"reason": "no_edge", "edge_yes": edge_yes, "edge_no": edge_no, "fair_prob": fair_prob, "mid": mid}
            return None
        
        # --- PHASE 8 FIX: FEE/SPREAD GATE ---
        dummy_qty = 10
        fee_est = calculate_convex_fee(price_to_pay, dummy_qty) / dummy_qty # $ per contract
        # use continuous per-contract fee estimate (no rounding artifacts)
        p = price_to_pay / 100.0
        fee_per_contract = 0.07 * p * (1 - p)   # dollars per contract (approx)
        fee_cents = fee_per_contract * 100.0
        
        required_edge_cents = fee_cents + self.margin_cents
        if (edge * 100) < required_edge_cents:
            self.last_decision = {
                "reason": "min_edge_fee_gate", 
                "edge_cents": edge * 100, 
                "required": required_edge_cents,
                "fair_prob": fair_prob,
                "mid": mid
            }
            return None

        edge_cents = edge * 100.0

        edge_after_fee = edge_cents - fee_cents - self.margin_cents
        if edge_after_fee <= 0:
            self.last_decision = {"reason": "edge_after_fee_negative", "edge_cents": edge_cents, "fee_cents": fee_cents, "margin": self.margin_cents, "mid": mid}
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
        if self.max_inventory is None:
            room = float('inf')
        else:
            room = self.max_inventory - current_inv
            if room <= 0:
                return None

        inv_penalty = 1.0 / (1.0 + current_inv / 200.0)

        qty = int(base_qty * scale * inv_penalty)
        if self.max_inventory is None:
            qty = max(1, qty)
        else:
            qty = max(1, min(qty, room))
        
        # Re-gate with actual fee (rounding check)
        fee_real = calculate_convex_fee(price_to_pay, qty)
        fee_cents_real = (fee_real / qty) * 100.0
        
        edge_after_fee_real = edge_cents - fee_cents_real - self.margin_cents
        if edge_after_fee_real <= 0:
            self.last_decision = {"reason": "real_fee_gate", "edge_after_fee_real": edge_after_fee_real, "mid": mid}
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
            
            orders.append({'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 'price': no_ask, 'expiry': current_time + timedelta(seconds=15), 'source': 'MM', 'time': current_time})
            
        self.last_debug = {"reason": "desired", "action": action, "qty": qty, "price": price_to_pay, "edge": edge}
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
        self.last_decision = {} # Added for debugging
        
    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        if "KXHIGHNY-26JAN09-B49.5" in ticker and "05:05:26" in str(current_time):
            print(f"DEBUG: RegimeSwitcher ENTERED for {ticker} at {current_time}")
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
        
        if scalper_orders is not None: combined.extend(scalper_orders)
        else: combined.extend(sc_active)
        
        # Capture debug info from MM
        if hasattr(self.mm, "last_debug") and self.mm.last_debug:
            self.last_decision = self.mm.last_debug
        else:
            self.last_decision = {"reason": "no_mm_debug"}

        return combined

# --- Complex Backtester ---
class ComplexBacktester:
    def __init__(
        self,
        start_time_midnight_filter: bool = False,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
        buy_slippage_cents: float = 0.0,
        seed_warmup_from_history: bool = False,
        round_prices_to_int: bool = False,
        min_requote_interval_seconds: float = 0.0,
        initial_capital: float | None = None,
        strategies: list[ComplexStrategy] | None = None,
        log_dir: str | None = None,
        charts_dir: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        generate_daily_charts: bool = True,
        generate_final_chart: bool = True,
        inventory_per_dollar_daily: float | None = None,
        enable_time_constraints: bool | None = None,
        **strategy_kwargs,
    ):
        self.generate_daily_charts = generate_daily_charts
        self.generate_final_chart = generate_final_chart
        self.inventory_per_dollar_daily = inventory_per_dollar_daily
        if enable_time_constraints is not None:
            global ENABLE_TIME_CONSTRAINTS
            ENABLE_TIME_CONSTRAINTS = bool(enable_time_constraints)

        self.log_dir = log_dir or LOG_DIR
        self.charts_dir = charts_dir or CHARTS_DIR
        if not os.path.exists(self.charts_dir):
            os.makedirs(self.charts_dir)

        self.strategies = strategies if strategies is not None else [
            RegimeSwitcher("Algo 3: Regime Switcher (Meta)", **strategy_kwargs)
        ]
        self.start_time_midnight_filter = start_time_midnight_filter
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.buy_slippage_cents = float(buy_slippage_cents or 0.0)
        self.seed_warmup_from_history = bool(seed_warmup_from_history)
        self.round_prices_to_int = bool(round_prices_to_int)
        self.min_requote_interval_seconds = float(min_requote_interval_seconds or 0.0)
        self.initial_capital = initial_capital if initial_capital is not None else INITIAL_CAPITAL
        start_date = START_DATE if start_date is None else start_date
        end_date = END_DATE if end_date is None else end_date

        def _parse_yymondd(s: str):
            try:
                return pd.Timestamp(datetime.strptime(s.strip(), "%y%b%d"))
            except Exception:
                return None

        if start_date:
            parsed = _parse_yymondd(str(start_date))
            self.start_date = parsed if parsed is not None else pd.to_datetime(start_date)
        else:
            self.start_date = None

        if end_date:
            parsed = _parse_yymondd(str(end_date))
            self.end_date = parsed if parsed is not None else pd.to_datetime(end_date)
        else:
            self.end_date = None
        self.warmup_start_date = pd.to_datetime(WARMUP_START_DATE) if 'WARMUP_START_DATE' in globals() and WARMUP_START_DATE else None
        self.performance_history = []
        self.portfolios = {}
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(self.initial_capital),
                'inventory_yes': defaultdict(lambda: defaultdict(int)), # source -> ticker -> qty
                'inventory_no': defaultdict(lambda: defaultdict(int)),
                'active_limit_orders': defaultdict(list),
                'trades': [],
                'pnl_by_source': defaultdict(float),
                'paid_out': set(), # Guard against double payouts
                'cost_basis': defaultdict(float) # ticker -> total cost basis
            }
        if self.inventory_per_dollar_daily is not None:
            for s in self.strategies:
                self._apply_inventory_cap_for_strategy(s, self.initial_capital)

    def _apply_inventory_cap_for_strategy(self, strategy, equity_value: float) -> None:
        if self.inventory_per_dollar_daily is None:
            return
        mm = getattr(strategy, "mm", None)
        if mm is None or not hasattr(mm, "max_inventory"):
            return
        try:
            cap = int(round(float(equity_value) * float(self.inventory_per_dollar_daily)))
        except Exception:
            cap = 0
        cap = max(1, cap)
        mm.max_inventory = cap

    def load_all_data(self):
        print(f"Loading data from {self.log_dir}...")
        files = sorted(glob.glob(os.path.join(self.log_dir, "market_data_*.csv")))
        
        # Filter by date
        filtered_files = []
        for f in files:
            date_str = os.path.basename(f).split('-')[-1].replace('.csv', '')
            try:
                file_dt = datetime.strptime(date_str, "%y%b%d")
            except Exception:
                # If we can't parse the file date, keep it (best-effort).
                filtered_files.append(f)
                continue

            if self.start_date is not None and file_dt < self.start_date:
                continue
            if self.end_date is not None and file_dt > self.end_date:
                continue
            filtered_files.append(f)
            
        if not filtered_files:
            print("No files found for the given date range.")
            return pd.DataFrame()
            
        dfs = []
        for f in filtered_files:
            try:
                df = pd.read_csv(f)
                df.columns = [c.strip() for c in df.columns]
                df['datetime'] = pd.to_datetime(df['timestamp'], format='mixed', dayfirst=True)
                # If we're seeding warmup from pre-start history, keep earlier ticks to build
                # strategy state, but trading will still be gated in run().
                if self.start_datetime is not None:
                    if self.seed_warmup_from_history:
                        start_floor = self.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
                        df = df[df['datetime'] >= start_floor]
                    else:
                        df = df[df['datetime'] >= self.start_datetime]
                if self.end_datetime is not None:
                    df = df[df['datetime'] <= self.end_datetime]
                dfs.append(df)
            except Exception as e:
                print(f"Error loading {f}: {e}")
                
        if not dfs: return pd.DataFrame()
        
        master_df = pd.concat(dfs, ignore_index=True)
        master_df.sort_values('datetime', inplace=True)
        # Vectorized date string pre-calculation
        master_df['date_str'] = master_df['datetime'].dt.strftime("%y%b%d").str.upper()
        return master_df
            
    def handle_market_expiries(self, portfolio, current_time, last_prices):
        """
        When a market ends, we convert held positions into an unsettled payout
        that becomes cash at 1AM next day (per your assumption).
        """
        wallet = portfolio['wallet']

        # Helper to queue payout and clear position
        def queue_payout(ticker, qty, is_yes: bool):
            if qty <= 0:
                return False
            end_time = market_end_time_from_ticker(ticker)
            pay_time = payout_time_from_ticker(ticker)
            if end_time is None or pay_time is None:
                return False
            if current_time < end_time:
                return False # not ended yet

            # Use last known mid as a proxy "final value" at expiry
            mid = last_prices.get(ticker, np.nan)
            
            # freeze at last mid, snap only near extremes
            settle_mid = settle_mid_price(mid)
            if pd.isna(settle_mid):
                return False

            if is_yes:
                value_per_contract = settle_mid / 100.0
            else:
                value_per_contract = (100.0 - settle_mid) / 100.0

            payout_amount = qty * value_per_contract

            # Money is locked until pay_time
            wallet.add_unsettled(payout_amount, pay_time)
            return True

        # YES inventories
        for src in list(portfolio['inventory_yes'].keys()):
            for tkr, qty in list(portfolio['inventory_yes'][src].items()):
                if qty > 0:
                    key = (src, tkr, 'YES')
                    if key in portfolio['paid_out']: continue
                    
                    if queue_payout(tkr, qty, is_yes=True):
                        portfolio['paid_out'].add(key)
                        portfolio['inventory_yes'][src][tkr] = 0
                        # Clear cost basis for this ticker if all sources are cleared
                        # (In this bot, usually only one source holds a ticker at a time)
                        portfolio['cost_basis'][tkr] = 0.0

        # NO inventories
        for src in list(portfolio['inventory_no'].keys()):
            for tkr, qty in list(portfolio['inventory_no'][src].items()):
                if qty > 0:
                    key = (src, tkr, 'NO')
                    if key in portfolio['paid_out']: continue
                    
                    if queue_payout(tkr, qty, is_yes=False):
                        portfolio['paid_out'].add(key)
                        portfolio['inventory_no'][src][tkr] = 0
                        portfolio['cost_basis'][tkr] = 0.0

    def execute_trade(self, portfolio, ticker, action, price, qty, source, timestamp, market_state, strat_name, viz_list):
        # 1. Apply optional buy-side slippage and calculate cost/fee
        exec_price = float(price)
        if action in ('BUY_YES', 'BUY_NO') and self.buy_slippage_cents:
            exec_price = min(100.0, exec_price + float(self.buy_slippage_cents))

        fee = calculate_convex_fee(exec_price, qty)
        cost = qty * (exec_price / 100.0) + fee
        
        # 2. Budget Check (Match Live Trader)
        start_equity = portfolio.get('daily_start_equity', self.initial_capital)
        risk_pct = 0.5
        for s in self.strategies:
            if s.name == strat_name:
                risk_pct = s.risk_pct
                break
        
        budget = start_equity * risk_pct
        
        # Calculate current exposure (Acquisition Cost)
        current_exposure = 0.0
        
        # Inventory Exposure (Cost Basis)
        current_exposure += sum(portfolio['cost_basis'].values())
                
        # Active Orders Exposure
        for t, orders in portfolio['active_limit_orders'].items():
            for o in orders:
                p_ord = o['price']
                q_ord = o['qty']
                current_exposure += q_ord * (p_ord / 100.0)
                
        if (current_exposure + cost) > budget:
            # Scale down to fit budget
            available = budget - current_exposure
            if available > 0 and cost > 0:
                ratio = available / cost
                qty = int(qty * ratio)
                if qty <= 0:
                    # print(f"BUDGET REJECT (Immediate) {ticker}: Exp=${current_exposure:.2f} + Cost=${cost:.2f} > Budget=${budget:.2f} (Scaled to 0)")
                    return False
                fee = calculate_convex_fee(price, qty)
                cost = qty * (price / 100.0) + fee
                # print(f"BUDGET SCALE (Immediate) {ticker}: Scaled qty to {qty} to fit budget ${budget:.2f}")
            else:
                # print(f"BUDGET REJECT (Immediate) {ticker}: Exp=${current_exposure:.2f} > Budget=${budget:.2f}")
                return False

        # 3. Check Cash & Execute
        if portfolio['wallet'].spend(cost):
            # Update Inventory
            if action == 'BUY_YES': 
                portfolio['inventory_yes'][source][ticker] += qty
            elif action == 'BUY_NO': 
                portfolio['inventory_no'][source][ticker] += qty
            
            # Update Cost Basis
            portfolio['cost_basis'][ticker] += cost
            
            y_ask = market_state.get('yes_ask', np.nan)
            y_bid = market_state.get('yes_bid', np.nan)
            
            spread_val = np.nan
            if not pd.isna(y_ask) and not pd.isna(y_bid): spread_val = y_ask - y_bid

            trade = {
                'time': timestamp, 
                'action': action, 
                'ticker': ticker, 
                'price': exec_price, 
                'qty': qty, 
                'fee': fee, 
                'cost': cost,
                'source': source, 
                'spread': spread_val, 
                'capital_after': portfolio['wallet'].available_cash
            }
            
            # Diagnostics
            mid_at_fill = (y_ask + y_bid) / 2.0 if (not pd.isna(y_ask) and not pd.isna(y_bid)) else np.nan
            if not pd.isna(mid_at_fill):
                if action == 'BUY_YES':
                    slippage = exec_price - mid_at_fill
                else:
                    slippage = exec_price - (100 - mid_at_fill)
                trade['slippage'] = slippage
                trade['mid_at_fill'] = mid_at_fill
            
            portfolio['trades'].append(trade)
            viz_list.append({**trade, 'strategy': strat_name, 'viz_y': 100-price if 'YES' in action else price})
            return True
            
        return False

    def check_limit_fills(self, portfolio, ticker, market_state, timestamp, viz_list, strat_name, last_prices):
        active = portfolio['active_limit_orders'][ticker]
        if not active: return
        
        y_ask = best_yes_ask(market_state)
        y_bid = best_yes_bid(market_state)
        n_ask = market_state.get('no_ask')
        n_bid = market_state.get('no_bid')
        
        # Calculate current spread for regime-aware fill probabilities
        spread_val = np.nan
        if not pd.isna(y_ask) and not pd.isna(y_bid):
            spread_val = y_ask - y_bid
            
        still_active = []
        for o in active:
            if 'expiry' in o and timestamp >= o['expiry']: continue
            
            filled = False
            l_price = o['price']
            action = o['action']
            qty = o['qty']
            source = o.get('source', 'Unknown')
            ticker = o['ticker'].strip()

            fill_price = None
            
            # Simple Fill Rule (Phase 6): If price crosses limit, fill.
            # Phase 7.5: Mutual Exclusivity Safety Net
            if action == 'BUY_YES':
                # Reject if we hold NO (Safety Net)
                if portfolio['inventory_no'][source][ticker] > 0:
                    still_active.append(o)
                    continue
                    
                if not pd.isna(y_ask) and y_ask <= l_price:
                    filled = True
                    fill_price = float(y_ask)
            elif action == 'BUY_NO': 
                # Reject if we hold YES (Safety Net)
                if portfolio['inventory_yes'][source][ticker] > 0:
                    still_active.append(o)
                    continue
                    
                if not pd.isna(n_ask) and n_ask <= l_price:
                    filled = True
                    fill_price = float(n_ask)
                            
            if filled:
                if fill_price is None:
                    still_active.append(o)
                    continue

                exec_price = float(fill_price)
                if action in ('BUY_YES', 'BUY_NO') and self.buy_slippage_cents:
                    exec_price = min(100.0, exec_price + float(self.buy_slippage_cents))

                fee = calculate_convex_fee(exec_price, qty)
                cost = (qty * (exec_price / 100.0)) + fee
                
                # --- BUDGET CHECK (Match Live Trader) ---
                start_equity = portfolio.get('daily_start_equity', self.initial_capital)
                risk_pct = 0.5
                for s in self.strategies:
                    if s.name == strat_name:
                        risk_pct = s.risk_pct
                        break
                budget = start_equity * risk_pct
                
                current_exposure = 0.0
                
                # 1. Inventory Exposure (Cost Basis)
                current_exposure += sum(portfolio['cost_basis'].values())
                        
                # 2. Active Orders Exposure
                for t, orders in portfolio['active_limit_orders'].items():
                    for ord_item in orders:
                        # Skip THIS order if it's in the list (it is)
                        if ord_item is o: continue
                        p = ord_item['price']
                        q = ord_item['qty']
                        current_exposure += q * (p / 100.0)
                
                if (current_exposure + cost) > budget:
                    # Scale down to fit budget
                    available = budget - current_exposure
                    if available > 0 and cost > 0:
                        ratio = available / cost
                        qty = int(qty * ratio)
                        if qty <= 0:
                            # print(f"BUDGET REJECT (Limit) {ticker}: Exp=${current_exposure:.2f} + Cost=${cost:.2f} > Budget=${budget:.2f} (Scaled to 0)")
                            still_active.append(o)
                            continue
                        fee = calculate_convex_fee(exec_price, qty)
                        cost = (qty * (exec_price / 100.0)) + fee
                        # print(f"BUDGET SCALE (Limit) {ticker}: Scaled qty to {qty} to fit budget ${budget:.2f}")
                    else:
                        # print(f"BUDGET REJECT (Limit) {ticker}: Exp=${current_exposure:.2f} > Budget=${budget:.2f}")
                        still_active.append(o)
                        continue

                # Check Cash
                if portfolio['wallet'].spend(cost):
                    # Update Inventory (Separate YES/NO)
                    if action == 'BUY_YES': 
                        portfolio['inventory_yes'][source][ticker] += qty
                    elif action == 'BUY_NO': 
                        portfolio['inventory_no'][source][ticker] += qty
                    
                    # Update Cost Basis
                    portfolio['cost_basis'][ticker] += cost
                    
                    trade = {
                        'time': timestamp, 
                        'action': action, 
                        'ticker': ticker, 
                        'price': exec_price, 
                        'qty': qty, 
                        'fee': fee, 
                        'cost': cost,
                        'source': source, 
                        'spread': spread_val, 
                        'capital_after': portfolio['wallet'].available_cash
                    }
                    
                    # Diagnostics
                    mid_at_fill = (y_ask + y_bid) / 2.0 if (not pd.isna(y_ask) and not pd.isna(y_bid)) else np.nan
                    if not pd.isna(mid_at_fill):
                        if action == 'BUY_YES':
                            slippage = exec_price - mid_at_fill
                        else:
                            slippage = exec_price - (100 - mid_at_fill)
                        trade['slippage'] = slippage
                        trade['mid_at_fill'] = mid_at_fill
                    
                    portfolio['trades'].append(trade)
                    viz_list.append({**trade, 'strategy': strat_name, 'viz_y': 100-exec_price if 'YES' in action else exec_price})
                    filled = True
                else:
                    filled = False
            
            if not filled:
                still_active.append(o)
        portfolio['active_limit_orders'][ticker] = still_active

    def liquidate_at_end(self, portfolio, ticker, market_state, current_time):
        end_t = market_end_time_from_ticker(ticker)
        if end_t is None or current_time < end_t:
            return

        yb = best_yes_bid(market_state)
        nb = market_state.get("no_bid", np.nan)
        
        # Liquidate YES inventory at YES_BID
        for src in list(portfolio["inventory_yes"].keys()):
            qty = portfolio["inventory_yes"][src].get(ticker, 0)
            if qty > 0 and not pd.isna(yb):
                price = float(yb)
                fee = calculate_convex_fee(price, qty)
                proceeds = qty * (price / 100.0) - fee
                portfolio["wallet"].add_cash(proceeds)
                portfolio["inventory_yes"][src][ticker] = 0
                portfolio['cost_basis'][ticker] = 0.0
                
                # Log the exit
                portfolio['trades'].append({
                    'time': current_time, 'action': 'SELL_YES', 'ticker': ticker, 
                    'price': price, 'qty': qty, 'fee': fee, 'source': src, 
                    'capital_after': portfolio['wallet'].available_cash,
                    'note': 'Forced Liquidation'
                })

        # Liquidate NO inventory at NO_BID
        for src in list(portfolio["inventory_no"].keys()):
            qty = portfolio["inventory_no"][src].get(ticker, 0)
            if qty > 0 and not pd.isna(nb):
                price = float(nb)
                fee = calculate_convex_fee(price, qty)
                proceeds = qty * (price / 100.0) - fee
                portfolio["wallet"].add_cash(proceeds)
                portfolio["inventory_no"][src][ticker] = 0
                portfolio['cost_basis'][ticker] = 0.0
                
                # Log the exit
                portfolio['trades'].append({
                    'time': current_time, 'action': 'SELL_NO', 'ticker': ticker, 
                    'price': price, 'qty': qty, 'fee': fee, 'source': src, 
                    'capital_after': portfolio['wallet'].available_cash,
                    'note': 'Forced Liquidation'
                })

        # cancel lingering orders after end
        portfolio["active_limit_orders"][ticker] = []

    def run(self):
        print("[ComplexBacktester] Global Loop Mode Starting...")
        
        # Load Data
        master_df = self.load_all_data()
        if master_df.empty: return
        
        last_prices = {}
        last_logged_date = None
        daily_trades_viz = []
        
        last_eval_ts: dict[tuple[str, str], datetime] = {}

        for idx, row in enumerate(master_df.itertuples(index=False)):
            current_time = row.datetime
            ticker = row.market_ticker
            current_date_str = row.date_str # Use pre-calculated date string
            
            is_warmup = self.warmup_start_date and current_time < self.start_date
            
            if current_date_str != last_logged_date:
                # End of previous day logic
                if last_logged_date is not None:
                    try:
                        completed_date_obj = datetime.strptime(last_logged_date, "%y%b%d").date()
                        sweep_time = datetime.combine(completed_date_obj, datetime.min.time()) + timedelta(days=1, hours=1, minutes=5)
                        
                        daily_report = {}
                        for s in self.strategies:
                            p = self.portfolios[s.name]
                            self.handle_market_expiries(p, sweep_time, last_prices)
                            p['wallet'].check_settlements(sweep_time)
                            
                            # Snapshot
                            cash = p['wallet'].available_cash
                            unsettled = sum(u['amount'] for u in p['wallet'].unsettled_positions)
                            holdings = 0
                            for src in p['inventory_yes']:
                                for t, q in p['inventory_yes'][src].items():
                                    mid = last_prices.get(t, np.nan)
                                    if not pd.isna(mid): holdings += q * (mid/100.0)
                            for src in p['inventory_no']:
                                for t, q in p['inventory_no'][src].items():
                                    mid = last_prices.get(t, np.nan)
                                    if not pd.isna(mid): holdings += q * ((100-mid)/100.0)
                            total_equity = cash + unsettled + holdings
                            
                            # UPDATE DAILY START EQUITY FOR NEXT DAY
                            p['daily_start_equity'] = total_equity
                            if self.inventory_per_dollar_daily is not None:
                                self._apply_inventory_cap_for_strategy(s, total_equity)
                            
                            daily_report[s.name] = {'start': self.initial_capital, 'equity': total_equity}
                            
                            if not hasattr(self, 'daily_equity_history'): self.daily_equity_history = defaultdict(list)
                            self.daily_equity_history[s.name].append({'date': last_logged_date, 'equity': total_equity, 'spendable_cash': cash})
                            print(f"[Day End {last_logged_date}] {s.name} Equity: ${total_equity:.2f} (Cash ${cash:.2f})")
                        
                        if self.generate_daily_charts:
                            self.generate_daily_chart(pd.DataFrame(), daily_trades_viz, daily_report, last_logged_date, last_prices)
                        daily_trades_viz = []
                    except Exception as e:
                        print(f"Error in Day End logic: {e}")
                        import traceback
                        traceback.print_exc()
                        
                last_logged_date = current_date_str
                
                # --- OPTIONAL: START AT MIDNIGHT OF EXPIRY DAY ---
                if self.start_time_midnight_filter:
                    try:
                        parts = ticker.split('-')
                        if len(parts) >= 2:
                            date_part = parts[1] # '25DEC24'
                            target_dt = datetime.strptime(date_part, "%y%b%d")
                            if current_time.date() < target_dt.date():
                                continue
                    except: pass
            
            yes_ask = getattr(row, 'implied_yes_ask', np.nan)
            no_ask = getattr(row, 'implied_no_ask', np.nan)
            yes_bid = getattr(row, 'best_yes_bid', np.nan)
            no_bid = getattr(row, 'best_no_bid', np.nan)

            if self.round_prices_to_int:
                yes_ask = int(round(float(yes_ask))) if not pd.isna(yes_ask) else np.nan
                no_ask = int(round(float(no_ask))) if not pd.isna(no_ask) else np.nan
                yes_bid = int(round(float(yes_bid))) if not pd.isna(yes_bid) else np.nan
                no_bid = int(round(float(no_bid))) if not pd.isna(no_bid) else np.nan

            ms = {
                'yes_ask': yes_ask,
                'no_ask': no_ask,
                'yes_bid': yes_bid,
                'no_bid': no_bid,
            }
            
            # --- PHASE 10 FIX: STOP UPDATING PRICES AFTER END ---
            end_t = market_end_time_from_ticker(ticker)
            
            yask = best_yes_ask(ms)
            ybid = best_yes_bid(ms)
            if not pd.isna(yask) and not pd.isna(ybid): 
                mid = (yask + ybid) / 2.0
                if end_t is None or current_time < end_t:
                    last_prices[ticker] = mid
            
            for s in self.strategies:
                # If snapshot replay starts mid-stream, optionally seed strategy state from pre-start ticks
                # without allowing trades/settlements before the trading window.
                if self.start_datetime is not None and current_time < self.start_datetime:
                    src_invs = {
                        'MM': {'YES': 0, 'NO': 0},
                        'Scalper': {'YES': 0, 'NO': 0}
                    }
                    s.on_market_update(ticker, ms, current_time, src_invs, [], self.portfolios[s.name]['wallet'].available_cash, idx)
                    continue

                # Warmup Mode: Update strategy state but DO NOT execute trades
                if is_warmup:
                    src_invs = {
                        'MM': {'YES': 0, 'NO': 0},
                        'Scalper': {'YES': 0, 'NO': 0}
                    }
                    s.on_market_update(ticker, ms, current_time, src_invs, [], self.portfolios[s.name]['wallet'].available_cash, idx)
                    continue

                p = self.portfolios[s.name]
                p['wallet'].check_settlements(current_time)
                
                # --- PHASE 11: FORCED LIQUIDATION AT BID ---
                self.liquidate_at_end(p, ticker, ms, current_time)
                
                self.handle_market_expiries(p, current_time, last_prices)
                self.check_limit_fills(p, ticker, ms, current_time, daily_trades_viz, s.name, last_prices)
                
                # Only run strategy if market is live
                if end_t is None or current_time < end_t:
                    # Optional live-parity: throttle strategy evaluation per (strategy,ticker)
                    if self.min_requote_interval_seconds > 0:
                        k = (s.name, ticker)
                        prev = last_eval_ts.get(k)
                        if prev is not None:
                            dt_s = (current_time - prev).total_seconds()
                            if dt_s < self.min_requote_interval_seconds:
                                continue

                    src_invs = {
                        'MM': {'YES': p['inventory_yes']['MM'][ticker], 'NO': p['inventory_no']['MM'][ticker]},
                        'Scalper': {'YES': p['inventory_yes']['Scalper'][ticker], 'NO': p['inventory_no']['Scalper'][ticker]}
                    }
                    new_orders = s.on_market_update(ticker, ms, current_time, src_invs, p['active_limit_orders'][ticker], p['wallet'].available_cash, idx)

                    if self.min_requote_interval_seconds > 0:
                        last_eval_ts[(s.name, ticker)] = current_time
                    
                    if new_orders is not None:
                         # --- IMMEDIATE FILL CHECK ---
                         active_orders = []
                         for o in new_orders:
                             filled = False
                             action = o['action']
                             price = o['price']
                             qty = o['qty']
                             source = o['source']
                             
                             if action == 'BUY_YES':
                                 curr_ask = ms.get('yes_ask', np.nan)
                                 if not pd.isna(curr_ask) and price >= curr_ask:
                                     filled = bool(self.execute_trade(p, ticker, action, float(curr_ask), qty, source, current_time, ms, s.name, daily_trades_viz))
                             elif action == 'BUY_NO':
                                 curr_ask = ms.get('no_ask', np.nan)
                                 if not pd.isna(curr_ask) and price >= curr_ask:
                                     filled = bool(self.execute_trade(p, ticker, action, float(curr_ask), qty, source, current_time, ms, s.name, daily_trades_viz))
                             
                             if not filled:
                                 active_orders.append(o)
                         
                         p['active_limit_orders'][ticker] = active_orders
            
            if idx % 10000 == 0:
                print(f"Processed {idx} ticks... Current: {current_time}")

        # Final Day End
        print("Final Day End logic...")
        for s in self.strategies:
            p = self.portfolios[s.name]
            self.handle_market_expiries(p, self.end_date + timedelta(days=1) if self.end_date else current_time + timedelta(days=1), last_prices)
            p['wallet'].check_settlements(self.end_date + timedelta(days=1) if self.end_date else current_time + timedelta(days=1))

            # Final Snapshot
            cash = p['wallet'].available_cash
            unsettled = sum(u['amount'] for u in p['wallet'].unsettled_positions)
            holdings = 0
            for src in p['inventory_yes']:
                for t, q in p['inventory_yes'][src].items():
                    mid = last_prices.get(t, np.nan)
                    if not pd.isna(mid): holdings += q * (mid/100.0)
            for src in p['inventory_no']:
                for t, q in p['inventory_no'][src].items():
                    mid = last_prices.get(t, np.nan)
                    if not pd.isna(mid): holdings += q * ((100-mid)/100.0)
            total_equity = cash + unsettled + holdings
            print(f"FINAL EQUITY [{s.name}]: ${total_equity:.2f}")

            # Ensure we record at least one day-end datapoint even when the run
            # doesn't cross a date boundary (common for snapshot/intraday replays).
            # This keeps reporting/runner charts stable.
            try:
                final_date_str = last_logged_date or current_time.strftime("%y%b%d").upper()
                p['daily_start_equity'] = total_equity
                if not hasattr(self, 'daily_equity_history'):
                    self.daily_equity_history = defaultdict(list)
                existing = self.daily_equity_history[s.name]
                if (not existing) or (existing[-1].get('date') != final_date_str):
                    self.daily_equity_history[s.name].append({'date': final_date_str, 'equity': total_equity, 'spendable_cash': cash})
            except Exception:
                pass

            total_fees = sum(t.get('fee', 0.0) for t in p.get('trades', []))
            print(
                f"FINAL BREAKDOWN [{s.name}]: Cash=${cash:.2f} | Unsettled=${unsettled:.2f} | Holdings=${holdings:.2f} | "
                f"Trades={len(p.get('trades', []))} | Fees=${total_fees:.2f}"
            )

        # --- NEW: DAILY ROI TABLE ---
        print("\n=== DAILY PERFORMANCE BREAKDOWN ===")
        print(f"{'Date':<10} | {'Equity':<10} | {'Daily %':<8} | {'Cum %':<8} | {'DD %':<8}")
        print("-" * 60)
        
        if hasattr(self, 'daily_equity_history'):
            for s_name, history in self.daily_equity_history.items():
                peak = self.initial_capital
                prev_equity = self.initial_capital
                
                for i, day_data in enumerate(history):
                    date = day_data['date']
                    equity = day_data['equity']
                    if equity > peak: peak = equity
                    dd_pct = ((peak - equity) / peak) * 100.0 if peak > 0 else 0
                    daily_ret = ((equity - prev_equity) / prev_equity) * 100.0 if prev_equity > 0 else 0
                    cum_ret = ((equity - self.initial_capital) / self.initial_capital) * 100.0
                    print(f"{date:<10} | ${equity:<9.2f} | {daily_ret:>7.2f}% | {cum_ret:>7.2f}% | {dd_pct:>7.2f}%")
                    prev_equity = equity

        # --- NEW: PORTFOLIO SNAPSHOT ---
        print("\n=== FINAL PORTFOLIO SNAPSHOT ===")
        for s in self.strategies:
            p = self.portfolios[s.name]
            print(f"Strategy: {s.name}")
            for src in p['inventory_yes']:
                for t, q in p['inventory_yes'][src].items():
                    if q > 0: print(f"  [YES] {t}: {q}")
            for src in p['inventory_no']:
                for t, q in p['inventory_no'][src].items():
                    if q > 0: print(f"  [NO]  {t}: {q}")
            
        # --- NEW: JSON DUMP FOR VERIFICATION ---
        final_inv = {'YES': {}, 'NO': {}}
        for s in self.strategies:
            p = self.portfolios[s.name]
            for src in p['inventory_yes']:
                for t, q in p['inventory_yes'][src].items():
                    if q > 0: final_inv['YES'][t] = final_inv['YES'].get(t, 0) + q
            for src in p['inventory_no']:
                for t, q in p['inventory_no'][src].items():
                    if q > 0: final_inv['NO'][t] = final_inv['NO'].get(t, 0) + q
        
        with open("debug_portfolio.json", "w") as f:
            json.dump(final_inv, f, indent=2)

        if self.generate_final_chart:
            self.generate_performance_chart()

    def generate_performance_chart(self):
        if not hasattr(self, 'daily_equity_history'): return
        _require_plotly()
        fig = go.Figure()
        for strat_name, history in self.daily_equity_history.items():
            dates = [h['date'] for h in history]
            equities = [h['equity'] for h in history]
            spendable = [h['spendable_cash'] for h in history]
            fig.add_trace(go.Scatter(x=dates, y=equities, mode='lines+markers', name=f"{strat_name} (NAV)"))
            fig.add_trace(go.Scatter(x=dates, y=spendable, mode='lines+markers', name=f"{strat_name} (Spendable Cash)", line=dict(dash='dot')))
        fig.update_layout(title="Strategy Value Over Time (Daily MTM Equity)", xaxis_title="Date", yaxis_title="Total Equity ($)", hovermode="x unified", height=800)
        fig.add_hline(y=self.initial_capital, line_dash="dash", line_color="gray", annotation_text="Initial Capital")
        filename = os.path.join(self.charts_dir, "final_performance_v3.html")
        fig.write_html(filename)
        print(f"Generated final performance chart: {filename}")

    def generate_daily_chart(self, df, trades, daily_report, date_str, last_prices):
        _require_plotly()
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.6, 0.15, 0.25], subplot_titles=(f"V3 Market & Trades - {date_str}", "Daily Performance", "Trade Log"), specs=[[{"type": "xy"}], [{"type": "table"}], [{"type": "table"}]])
        if not df.empty:
            tickers = df['market_ticker'].unique()[:15]
            for t in tickers:
                m = df[df['market_ticker'] == t]
                fig.add_trace(go.Scatter(x=m['timestamp'], y=m['implied_no_ask'], mode='lines', name=t, opacity=0.4), row=1, col=1)
        for t in trades[:500]:
            color = 'blue' if 'BUY' in t['action'] else 'red'
            symbol = 'circle' if t['source'] == 'MM' else 'diamond'
            fig.add_trace(go.Scatter(x=[t['time']], y=[t['viz_y']], mode='markers', marker=dict(color=color, size=9, symbol=symbol), name=f"{t['source']} {t['action']}"), row=1, col=1)
        fig.add_trace(go.Table(header=dict(values=["Strategy", "End Equity (MTM)"]), cells=dict(values=list(zip(*[[s, f"${d['equity']:.2f}"] for s, d in daily_report.items()])))), row=2, col=1)
        
        trade_data = []
        chart_time = df['datetime'].max() if not df.empty else datetime.now()
        for t in trades:
            end_price = last_prices.get(t['ticker'], np.nan)
            end_t = market_end_time_from_ticker(t['ticker'])
            if end_t and chart_time >= end_t:
                end_price = settle_mid_price(last_prices.get(t['ticker'], np.nan))
            roi = np.nan
            if not pd.isna(end_price):
                val = end_price if 'YES' in t['action'] else (100 - end_price)
                roi = ((val / 100.0 * t['qty']) - t['cost']) / t['cost']
            trade_data.append([t['time'].strftime("%H:%M"), t['ticker'], t['source'], t['action'], f"{t['price']}c", t['qty'], f"${t['cost']:.2f}", f"{end_price:.1f}c" if not pd.isna(end_price) else "-", f"{roi*100:+.1f}%" if not pd.isna(roi) else "-"])
        fig.add_trace(go.Table(header=dict(values=["Time", "Ticker", "Source", "Action", "Price", "Qty", "Cost", "End Price", "ROI"]), cells=dict(values=list(zip(*trade_data)))), row=3, col=1)
        fig.update_layout(height=1000, title_text=f"Complex V3: {date_str}")
        fig.write_html(os.path.join(self.charts_dir, f"complex_v3_{date_str}.html"))

if __name__ == "__main__":
    ComplexBacktester().run()

def make_strategy():
    return InventoryAwareMarketMaker(name="test_strat")
