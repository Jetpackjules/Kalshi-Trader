from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import math
import time
import base64
import json
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding


KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
API_URL = "https://api.elections.kalshi.com"


def calculate_convex_fee(price: float, qty: int) -> float:
    p = price / 100.0
    raw_fee = 0.07 * qty * p * (1 - p)
    return math.ceil(raw_fee * 100) / 100.0


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


@dataclass
class OrderResult:
    ok: bool
    filled: int
    status: str


class BaseAdapter:
    def process_tick(self, ticker: str, market_state: dict, current_time: datetime) -> None:
        return None

    def get_open_orders(self, ticker: str, market_state: dict, current_time: datetime) -> list[dict]:
        raise NotImplementedError

    def cancel_order(self, order_id: str | None) -> None:
        raise NotImplementedError

    def place_order(self, order, market_state: dict, current_time: datetime) -> OrderResult:
        raise NotImplementedError

    def get_positions(self) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    def get_cash(self) -> float:
        raise NotImplementedError

    def get_latest_market_state(self, ticker: str) -> dict | None:
        return None


class SimAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        initial_cash: float = 0.0,
        initial_positions: dict[str, dict[str, Any]] | None = None,
        diag_log=None,
        fill_latency_s: float = 0.0,
        fill_latency_sampler=None,
        fill_prob_per_min: float = 0.0,
    ):
        self.cash = float(initial_cash)
        self.positions: dict[str, dict[str, Any]] = initial_positions or {}
        self.open_orders: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self.order_history: list[dict[str, Any]] = []
        self._order_id = 0
        self._diag_log = diag_log
        self._fill_latency_s = max(0.0, float(fill_latency_s))
        self._fill_latency_sampler = fill_latency_sampler
        self.last_prices: dict[str, float] = {}
        self.last_market_state: dict[str, dict[str, float | None]] = {}
        # Convert per-minute probability to per-second (approx)
        # P(fill in 1 sec) = 1 - (1 - P_min)^(1/60)
        # Or just linear approx if P is small: P_sec = P_min / 60
        self._fill_prob_per_sec = float(fill_prob_per_min) / 60.0
        
        # Deterministic Simulation
        import random
        random.seed(42)

    def _sample_fill_latency(self) -> float:
        if self._fill_latency_sampler:
            try:
                return max(0.0, float(self._fill_latency_sampler()))
            except Exception:
                return self._fill_latency_s
        return self._fill_latency_s

    def _next_id(self) -> str:
        self._order_id += 1
        return f"SIM_{self._order_id}"

    def process_tick(self, ticker: str, market_state: dict, current_time: datetime) -> None:
        self.last_market_state[ticker] = {
            "yes_ask": market_state.get("yes_ask"),
            "no_ask": market_state.get("no_ask"),
            "yes_bid": market_state.get("yes_bid"),
            "no_bid": market_state.get("no_bid"),
            "last_price": market_state.get("last_price"),
        }
        # Track last mid price for settlement
        ya = market_state.get("yes_ask")
        yb = market_state.get("yes_bid")
        if ya is not None and yb is not None:
            self.last_prices[ticker] = (float(ya) + float(yb)) / 2.0
        elif ya is not None:
            self.last_prices[ticker] = float(ya)
        elif yb is not None:
            self.last_prices[ticker] = float(yb)

        self._fill_resting_orders(ticker, market_state, current_time)

    def get_open_orders(self, ticker: str, market_state: dict, current_time: datetime) -> list[dict]:
        self._fill_resting_orders(ticker, market_state, current_time)
        return [o for o in self.open_orders if o.get("ticker") == ticker]

    def cancel_order(self, order_id: str | None) -> None:
        if order_id is None:
            return
        for o in self.open_orders:
            if o.get("order_id") == order_id:
                o["status"] = "canceled"
                o["remaining_count"] = 0
        self.open_orders = [o for o in self.open_orders if o.get("remaining_count", 0) > 0]

    def place_order(self, order, market_state: dict, current_time: datetime) -> OrderResult:
        side = "yes" if order.action == "BUY_YES" else "no"
        price = float(order.price)
        qty = int(order.qty)
        order_id = self._next_id()

        fill_latency_s = self._sample_fill_latency()
        new_order = {
            "order_id": order_id,
            "ticker": order.ticker,
            "side": side,
            "yes_price": price if side == "yes" else None,
            "no_price": price if side == "no" else None,
            "is_close": bool(getattr(order, "is_close", False)),
            "remaining_count": qty,
            "status": "open",
            "order_time": current_time,
            "ready_at": current_time + timedelta(seconds=fill_latency_s),
            "fill_latency_s": fill_latency_s,
        }

        filled = self._maybe_fill(new_order, market_state, current_time)
        if filled:
            if self._diag_log:
                self._diag_log(
                    "TRADE",
                    tick_ts=current_time,
                    ticker=order.ticker,
                    side=side,
                    price=price,
                    qty=qty,
                    status="executed",
                )
            self.order_history.append(
                {
                    "time": current_time,
                    "ticker": order.ticker,
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "status": "executed",
                    "filled": filled,
                    "order_id": order_id,
                    "order_time": current_time,
                    "ready_at": new_order.get("ready_at"),
                    "fill_latency_s": fill_latency_s,
                }
            )
            return OrderResult(ok=True, filled=filled, status="executed")

        if new_order.get("status") == "rejected_cash":
            self.order_history.append(
                {
                    "time": current_time,
                    "ticker": order.ticker,
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "status": "rejected_cash",
                    "filled": 0,
                    "order_id": order_id,
                    "order_time": current_time,
                    "ready_at": new_order.get("ready_at"),
                    "fill_latency_s": fill_latency_s,
                }
            )
            return OrderResult(ok=False, filled=0, status="rejected_cash")

        self.open_orders.append(new_order)
        if self._diag_log:
            self._diag_log(
                "ORDER",
                tick_ts=current_time,
                ticker=order.ticker,
                side=side,
                price=price,
                qty=qty,
                status="resting",
            )
        self.order_history.append(
            {
                "time": current_time,
                "ticker": order.ticker,
                "side": side,
                "price": price,
                "qty": qty,
                "status": "resting",
                "filled": 0,
                "order_id": order_id,
                "order_time": current_time,
                "ready_at": new_order.get("ready_at"),
                "fill_latency_s": fill_latency_s,
            }
        )
        return OrderResult(ok=True, filled=0, status="resting")

    def _maybe_fill(self, order: dict, market_state: dict, current_time: datetime) -> int:
        side = order["side"]
        price = float(order["yes_price"] if side == "yes" else order["no_price"])
        qty = int(order["remaining_count"])
        if qty <= 0:
            return 0

        # 1. Active Fill (Crossing the Spread)
        ask = market_state.get("yes_ask") if side == "yes" else market_state.get("no_ask")
        if ask is not None and price >= float(ask):
             if self._fill_order(order, price=float(ask), qty=qty, current_time=current_time):
                 return qty
             return 0

        # 2. Passive Fill (Market moves through our Limit)
        # Throttled by fill_prob_per_min to match reality
        last_price = market_state.get("last_price")
        if last_price is not None:
            lp = float(last_price)
            
            # Check probability first (Throttle)
            import random
            # Use fill_prob_per_min directly as a "capture rate" for observed trades
            # Since this is called per tick, and ticks are frequent, we need to be careful.
            # But wait, fill_prob_per_min was converted to fill_prob_per_sec.
            # Let's use fill_prob_per_sec as the probability to capture THIS specific trade.
            if self._fill_prob_per_sec > 0 and random.random() < self._fill_prob_per_sec:
                # If we are buying YES at P, and a trade happens at <= P, we might have been filled.
                if side == "yes":
                    if lp <= price:
                        if self._fill_order(order, price=lp, qty=qty, current_time=current_time):
                            return qty
                        return 0
                else:
                    # Buying NO at P means Selling YES at 100-P.
                    # If trade happens at >= 100-P, we (as sellers of YES) got filled.
                    implied_yes_ask = 100.0 - price
                    if lp >= implied_yes_ask:
                        fill_price_no = 100.0 - lp
                        if self._fill_order(order, price=fill_price_no, qty=qty, current_time=current_time):
                            return qty
                        return 0
        
        # 3. Probabilistic Fill (Simulate liquidity taking)
        # DISABLED: Using Throttled Passive Fills instead.
        # if self._fill_prob_per_sec > 0:
        #     import random
        #     if random.random() < self._fill_prob_per_sec:
        #         # Assume filled at limit price (conservative)
        #         if self._fill_order(order, price=price, qty=qty, current_time=current_time):
        #             return qty
        #         return 0

        ready_at = order.get("ready_at")
        if ready_at and current_time < ready_at:
            return 0

        return 0

    def _fill_order(self, order: dict, *, price: float, qty: int, current_time: datetime) -> bool:
        ticker = order["ticker"]
        side = order["side"]
        fee = calculate_convex_fee(price, qty)
        cost = qty * (price / 100.0) + fee
        is_close = bool(order.get("is_close", False))
        if self.cash < cost:
            pos = self.positions.get(ticker, {})
            opp_side = "no" if side == "yes" else "yes"
            opp_qty = int(pos.get(opp_side, 0) or 0)
            can_net_close = is_close and opp_qty >= qty
            if not can_net_close:
                message = (
                    "ERROR_SIM_CASH_REJECT "
                    f"ticker={ticker} side={side} qty={qty} fill_price={price:.2f} "
                    f"cost={cost:.2f} cash={self.cash:.2f} is_close={is_close}"
                )
                print(message)
                order["remaining_count"] = 0
                order["status"] = "rejected_cash"
                if self._diag_log:
                    self._diag_log(
                        "TRADE",
                        tick_ts=current_time,
                        ticker=ticker,
                        side=side,
                        price=price,
                        qty=qty,
                        fee=fee,
                        cost=cost,
                        status="rejected_cash",
                    )
                return False

        pos = self.positions.setdefault(ticker, {"yes": 0, "no": 0, "cost": 0.0})
        if side == "yes":
            pos["yes"] += qty
        else:
            pos["no"] += qty
        pos["cost"] += cost
        self.cash -= cost

        # Netting Logic
        yes_qty = pos["yes"]
        no_qty = pos["no"]
        if yes_qty > 0 and no_qty > 0:
            net_qty = min(yes_qty, no_qty)
            pos["yes"] -= net_qty
            pos["no"] -= net_qty
            credit = net_qty * 1.00
            self.cash += credit

        order["remaining_count"] = 0
        order["status"] = "executed"

        order_time = order.get("order_time") or current_time
        fill_delay_s = (current_time - order_time).total_seconds()
        self.trades.append(
            {
                "time": current_time,
                "action": "BUY_YES" if side == "yes" else "BUY_NO",
                "ticker": ticker,
                "price": price,
                "qty": qty,
                "fee": fee,
                "cost": cost,
                "source": "SIM",
                "order_id": order.get("order_id"),
                "order_time": order_time,
                "fill_time": current_time,
                "fill_delay_s": fill_delay_s,
                "place_time": None,
            }
        )
        if self._diag_log:
            self._diag_log(
                "TRADE",
                tick_ts=current_time,
                ticker=ticker,
                side=side,
                price=price,
                qty=qty,
                fee=fee,
                cost=cost,
                status="filled",
            )
        return True

    def get_latest_market_state(self, ticker: str) -> dict | None:
        state = self.last_market_state.get(ticker)
        if not state:
            return None
        return dict(state)

    def _fill_resting_orders(self, ticker: str, market_state: dict, current_time: datetime) -> None:
        remaining = []
        for order in self.open_orders:
            if order.get("ticker") != ticker:
                remaining.append(order)
                continue
            filled = self._maybe_fill(order, market_state, current_time)
            if not filled and order.get("remaining_count", 0) > 0:
                remaining.append(order)
        self.open_orders = remaining

    def get_positions(self) -> dict[str, dict[str, Any]]:
        return self.positions

    def get_cash(self) -> float:
        return self.cash

    def settle_market(self, ticker: str, settlement_price: float, current_time: datetime) -> float:
        """
        Settles a market for the given ticker at the specified settlement price (0 or 100).
        Returns the total payout amount.
        """
        pos = self.positions.get(ticker)
        if not pos:
            return 0.0

        yes_qty = int(pos.get("yes", 0))
        no_qty = int(pos.get("no", 0))
        
        # Calculate payout
        # If settlement_price is 100 (YES wins): YES pays $1, NO pays $0
        # If settlement_price is 0 (NO wins): YES pays $0, NO pays $1
        # We assume settlement_price is in cents (0 or 100) or dollars (0 or 1)? 
        # Kalshi usually uses cents (100 cents = $1). Let's support 0-100 scale.
        
        payout_per_yes = settlement_price / 100.0
        payout_per_no = (100.0 - settlement_price) / 100.0
        
        total_payout = (yes_qty * payout_per_yes) + (no_qty * payout_per_no)
        
        if total_payout > 0:
            self.cash += total_payout
            if self._diag_log:
                self._diag_log(
                    "SETTLEMENT",
                    tick_ts=current_time,
                    ticker=ticker,
                    payout=total_payout,
                    cash_after=self.cash
                )
        
        # Clear position
        del self.positions[ticker]
        
        return total_payout


class LiveAdapter(BaseAdapter):
    def __init__(self, key_path: str, diag_log=None, fills_log=None, fills_poll_interval=10.0):
        self._diag_log = diag_log
        self._fills_log = fills_log
        try:
            with open(key_path, 'rb') as f:
                self.private_key = serialization.load_pem_private_key(f.read(), password=None)
        except Exception as e:
            raise RuntimeError(f"Failed to load private key from {key_path}: {e}")

        self._session = requests.Session()
        
        # Caches
        self._cash = 0.0
        self._portfolio_value = 0.0
        self._positions = {}
        self._last_sync_time = 0.0
        self._sync_interval = 60.0
        
        self._open_orders_cache = {} # {ticker: (timestamp, orders)}
        self._orders_cache_ttl = 10.0

        # Fills polling
        self._fills_last_poll = 0.0
        self._fills_poll_interval = float(fills_poll_interval)
        self._fills_limit = 50
        self._fills_cursor = None
        self._fills_initialized = False
        # Dedupe fills by time/order_id in case cursor is missing or unreliable.
        self._fills_last_seen_time = None
        self._fills_last_seen_ids = set()
        # Map order_id -> client_order_id to backfill fills when API omits client IDs.
        self._client_id_by_order_id = {}
        
        # Track session trades
        # Track session trades
        self.trades = []
        self.order_history = []
        
        # Pending Deductions (Race Condition Fix)
        self._pending_deductions = [] # list of {"time": ts, "cost": amt}

        # Initial Sync
        self._sync_state()
        
        # Cleanup: Cancel any existing orders from previous runs (orphans)
        self._cancel_all_startup()

    def _cancel_all_startup(self):
        try:
            print("DEBUG: Canceling all existing orders on startup...")
            # Fetch all orders (no ticker filter to catch everything)
            path = "/trade-api/v2/portfolio/orders?status=active"
            headers = create_headers(self.private_key, "GET", path)
            resp = self._session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                orders = resp.json().get("orders", [])
                for o in orders:
                    oid = o.get("order_id")
                    print(f"DEBUG: Canceling orphan order {oid} ({o.get('ticker')} {o.get('type')})")
                    self.cancel_order(oid)
            else:
                print(f"DEBUG: Failed to fetch startup orders: {resp.text}")
        except Exception as e:
            print(f"DEBUG: Startup cleanup failed: {e}")

    def process_tick(self, ticker: str, market_state: dict, current_time: datetime) -> None:
        # Cache market state for Engine lookups (Cross-Ticker Trading)
        if not hasattr(self, "last_market_state"):
            self.last_market_state = {}
        self.last_market_state[ticker] = market_state

        # Poll fills at low frequency for logging/attribution.
        self._poll_fills()

    def _poll_fills(self) -> None:
        if not self._fills_log:
            return
        now = time.time()
        


        # Optimization: Don't poll aggressively for fills (history only)
        if now - self._fills_last_poll < self._fills_poll_interval:
            return
        self._fills_last_poll = now

        min_ts_param = ""

    def get_latest_market_state(self, ticker: str) -> dict | None:
        if not hasattr(self, "last_market_state"):
            return None
        return self.last_market_state.get(ticker)
        if self._fills_last_seen_time:
             ts_val = int(self._fills_last_seen_time.timestamp())
             min_ts_param = f"&min_ts={ts_val}"

        path = f"/trade-api/v2/portfolio/fills?limit={self._fills_limit}{min_ts_param}"
        headers = create_headers(self.private_key, "GET", path)
        try:
            resp = self._session.get(API_URL + path, headers=headers)
        except Exception as e:
            if self._diag_log:
                self._diag_log("ERROR", msg=f"fills poll exception: {e}")
            return

        if resp.status_code != 200:
            if self._diag_log:
                self._diag_log("ERROR", msg=f"fills poll failed: {resp.status_code}")
            return

        data = resp.json() if resp.text else {}
        fills = data.get("fills", [])
        # We ignore cursor from API, we only want forward-moving time filtering.

        parsed = []
        for f in fills:
            ts = self._parse_fill_time(
                f.get("created_time") or f.get("fill_time") or f.get("time")
            )
            parsed.append((ts, f))

        parsed.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc))

        for ts, f in parsed:
            if ts is None:
                continue
            # If no cursor support, fall back to last seen time gate.
            if not self._fills_cursor and self._fills_last_seen_time and ts <= self._fills_last_seen_time:
                continue

            # Extra check: If we use min_ts, we might get the same second fills again.
            # Dedupe by Order ID + TS.
            key = (
                f.get("order_id"),
                ts.isoformat(),
                f.get("side"),
                f.get("price"),
                f.get("count"),
            )
            if key in self._fills_last_seen_ids:
                continue

            self._fills_last_seen_ids.add(key)
            if len(self._fills_last_seen_ids) > 5000: # Use literal if constant missing
                # Trim to avoid unbounded growth.
                self._fills_last_seen_ids = set(list(self._fills_last_seen_ids)[-2000:])

            if not self._fills_last_seen_time or ts > self._fills_last_seen_time:
                self._fills_last_seen_time = ts

            fill_time = None
            if hasattr(self, "_format_fill_time"):
                 fill_time = self._format_fill_time(ts)
            else:
                 fill_time = ts.isoformat()
            
            liquidity = f.get("liquidity")
            if not liquidity:
                if f.get("is_taker") is True:
                    liquidity = "taker"
                elif f.get("is_maker") is True:
                    liquidity = "maker"

            # Backfill client_order_id if missing, using cached order_id -> client_order_id.
            client_order_id = (
                f.get("client_order_id")
                or f.get("clientOrderId")
                or f.get("client_order")
                or f.get("client_id")
            )
            if not client_order_id and f.get("order_id"):
                client_order_id = self._client_id_by_order_id.get(f.get("order_id"))

            if self._fills_log:
                self._fills_log({
                    "fill_time": fill_time,
                    "ticker": f.get("ticker"),
                    "side": f.get("side"),
                    "price": f.get("price"),
                    "qty": f.get("count") or f.get("qty"),
                    "liquidity": liquidity,
                    "order_id": f.get("order_id"),
                    "client_order_id": client_order_id or "",
                    "fee": f.get("fee"),
                    "raw_fee": f.get("raw_fee"),
                    "source": "api",
                })

        self._fills_initialized = True

    @staticmethod
    def _parse_fill_time(ts: str | None) -> datetime | None:
        if not ts:
            return None
        s = ts.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _sync_state(self):
        try:
            # 1. Balance
            path = "/trade-api/v2/portfolio/balance"
            headers = create_headers(self.private_key, "GET", path)
            resp = self._session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                new_cash = float(data.get("balance", 0.0)) / 100.0
                print(f"DEBUG: Sync Cash | Old: {self._cash:.2f} | New (API): {new_cash:.2f}")
                self._cash = new_cash # API returns cents
                self._portfolio_value = float(data.get("portfolio_value", 0.0)) / 100.0
            
            # 2. Positions
            path = "/trade-api/v2/portfolio/positions"
            headers = create_headers(self.private_key, "GET", path)
            resp = self._session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                self._positions = {}
                for p in data.get("market_positions", []):
                    ticker = p.get("ticker")
                    raw_qty = p.get("position", 0)
                    qty = abs(raw_qty)
                    
                    if qty > 0:
                        exposure = p.get("market_exposure", 0)
                        fees = p.get("fees_paid", 0)
                        cost = (exposure + fees) / 100.0
                        
                        if ticker not in self._positions:
                            self._positions[ticker] = {"yes": 0, "no": 0, "cost": 0.0}
                        
                        if raw_qty > 0:
                            self._positions[ticker]["yes"] = qty
                        else:
                            self._positions[ticker]["no"] = qty
                        
                        self._positions[ticker]["cost"] = cost
                        # Store last price if available (for value estimation)
                        self._positions[ticker]["last_price"] = float(p.get("last_price", 0)) / 100.0
                        
                        print(f"DEBUG: Synced Position | {ticker} | YES={self._positions[ticker]['yes']} | NO={self._positions[ticker]['no']}")




            self._last_sync_time = time.time()
        except Exception as e:
            if self._diag_log:
                self._diag_log("ERROR", msg=f"Sync failed: {e}")

    def get_cash(self) -> float:
        if time.time() - self._last_sync_time > self._sync_interval:
            print("DEBUG: get_cash triggering sync...")
            self._sync_state()
            
        # Deduct pending orders (Fix for race condition)
        # We trust our local deduction for 5 seconds until API catches up.
        now = time.time()
        self._pending_deductions = [d for d in self._pending_deductions if now - d["time"] < 5.0]
        pending = sum(d["cost"] for d in self._pending_deductions)
        
        effective_cash = self._cash - pending
        if pending > 0:
             # Debug log for verification
             pass 
             
        return max(0.0, effective_cash)

    def get_portfolio_value(self) -> float:
        if time.time() - self._last_sync_time > self._sync_interval:
            self._sync_state()
        return self._portfolio_value

    def get_positions(self) -> dict[str, dict[str, Any]]:
        if time.time() - self._last_sync_time > self._sync_interval:
            self._sync_state()
        return self._positions

    def get_open_orders(self, ticker: str, market_state: dict, current_time: datetime) -> list[dict]:
        # Improved Caching: Use logic that caches ALL orders once, then filters locally.
        
        # Check Global Cache (avoids N api calls for N tickers)
        # self._global_orders_cache = (timestamp, all_orders_list)
        if not hasattr(self, "_global_orders_cache"):
            self._global_orders_cache = (0.0, [])

        cache_ts, all_orders = self._global_orders_cache
        now = time.time()
        
        # If cache is old, refresh it
        if now - cache_ts > self._orders_cache_ttl:
            # We must fetch both 'open' and 'resting' orders to have a complete picture.
            all_orders_data = []
            
            for status in ["open", "resting"]:
                path = f"/trade-api/v2/portfolio/orders?status={status}"
                headers = create_headers(self.private_key, "GET", path)
                try:
                    resp = self._session.get(API_URL + path, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        all_orders_data.extend(data.get("orders", []))
                    elif self._diag_log:
                        self._diag_log("ERROR", msg=f"Get orders({status}) failed: {resp.status_code}")
                except Exception as e:
                    if self._diag_log:
                        self._diag_log("ERROR", msg=f"Get orders({status}) exception: {e}")

            all_orders = []
            seen_ids = set()
            
            for o in all_orders_data:
                 if o.get("order_id") in seen_ids:
                     continue
                 seen_ids.add(o.get("order_id"))
                 
                 if o.get("status") not in ("resting", "open"):
                     continue
                 
                 # Safe casting and normalizing
                 yp = o.get("yes_price")
                 np = o.get("no_price")
                 rc = o.get("remaining_count")
                 
                 norm_order = {
                    "order_id": o.get("order_id"),
                    "client_order_id": o.get("client_order_id"),
                    "ticker": o.get("ticker"),
                    "side": o.get("side"),
                    "yes_price": int(yp) if yp is not None else None,
                    "no_price": int(np) if np is not None else None,
                    "remaining_count": int(rc) if rc is not None else 0,
                    "status": o.get("status"),
                    "created_time": o.get("created_time"),
                    "action": o.get("action"), 
                 }
                 all_orders.append(norm_order)
                 
                 # Backfill client ID cache
                 if o.get("order_id") and o.get("client_order_id"):
                     self._client_id_by_order_id[o.get("order_id")] = o.get("client_order_id")
                     
            self._global_orders_cache = (now, all_orders)
        
        # Filter from Global Cache
        ticker_orders = [o for o in all_orders if o.get("ticker") == ticker]
        return ticker_orders

    def get_open_orders_all(self) -> list[dict]:
        path = "/trade-api/v2/portfolio/orders?status=open"
        headers = create_headers(self.private_key, "GET", path)
        try:
            resp = self._session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                orders = []
                for o in data.get("orders", []):
                    if o.get("status") not in ("resting", "open"):
                        continue
                    orders.append(o)
                return orders
        except Exception as e:
            if self._diag_log:
                self._diag_log("ERROR", msg=f"Get orders(all) failed: {e}")
        return []

    def cancel_order(self, order_id: str | None) -> None:
        if not order_id: return
        path = f"/trade-api/v2/portfolio/orders/{order_id}"
        headers = create_headers(self.private_key, "DELETE", path)
        try:
            self._session.delete(API_URL + path, headers=headers)
            # Invalidate cache? Hard to know which ticker.
            self._open_orders_cache = {} # Clear all to be safe
        except Exception:
            pass
            
    def cancel_all_orders(self) -> None:
        """Emergency cleanup: fetch all open/resting orders and cancel them."""
        orders = []
        for s in ["open", "resting"]:
            path = f"/trade-api/v2/portfolio/orders?status={s}"
            headers = create_headers(self.private_key, "GET", path)
            try:
                resp = self._session.get(API_URL + path, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    orders.extend(data.get("orders", []))
            except Exception as e:
                if self._diag_log:
                    self._diag_log("ERROR", msg=f"CancelAll fetch {s} failed: {e}")

        # Dedupe
        seen = set()
        unique = []
        for o in orders:
            oid = o.get("order_id")
            if oid not in seen:
                seen.add(oid)
                unique.append(o)
                
        if unique and self._diag_log:
            self._diag_log("INFO", msg=f"CancelAll: Found {len(unique)} orders to nuke.")
        elif unique:
            print(f"CancelAll: Found {len(unique)} orders to nuke.")

        for o in unique:
            self.cancel_order(o.get("order_id"))
            time.sleep(0.05) # Rate limit safety

    def place_order(self, order, market_state: dict, current_time: datetime) -> OrderResult:
        # order is an object or dict from Engine
        # Engine passes 'Order' object or dict.
        # Engine.py: self.adapter.place_order(order, ...)
        # order has .action, .ticker, .qty, .price, .side (derived)
        # Action semantics:
        # - BUY_YES open = buy YES (spends cash)
        # - BUY_NO open  = buy NO (spends cash)
        # - BUY_NO close (against YES) maps to API sell YES (generates cash)
        # - BUY_YES close (against NO) maps to API sell NO (generates cash)
        side = "yes" if order.action == "BUY_YES" else "no"
        price = int(order.price) # API expects integer cents? Or not?
        qty = int(order.qty)
        ticker = order.ticker
        client_order_id = getattr(order, "client_order_id", None)
        order_is_close = bool(getattr(order, "is_close", False))

        def _submit_order(*, api_action: str, api_side: str, order_price: int, order_qty: int, is_close: bool, orig_action: str) -> OrderResult:
            payload = {
                "action": api_action,
                "ticker": ticker,
                "count": int(order_qty),
                "type": "limit",
                "side": api_side,
                "yes_price": order_price if api_side == "yes" else None,
                "no_price": order_price if api_side == "no" else None,
                "client_order_id": client_order_id,
            }
            if is_close:
                print(f"DEBUG: Using Native Sell (GTC) | {api_action.upper()} {api_side.upper()} {order_qty}")
                # Ensure close orders only reduce existing inventory.
                payload["reduce_only"] = True
                # Kalshi only allows reduce_only with IoC.
                payload["time_in_force"] = "immediate_or_cancel"
            payload = {k: v for k, v in payload.items() if v is not None}

            # --- PRE-FLIGHT CASH CHECK ---
            try:
                can_afford = True
                cost = 0.0
                if api_action == "buy":
                    fee = calculate_convex_fee(order_price, int(order_qty))
                    cost = (int(order_qty) * (order_price / 100.0)) + fee
                    if self.get_cash() < cost:
                        can_afford = False
                        opp_side = "yes" if api_side == "no" else "no"
                        pos = self._positions.get(ticker, {})
                        opp_qty = pos.get(opp_side, 0)
                        print(f"DEBUG: Netting Check | Ticker: {ticker} | Side: {api_side} | Opp Side: {opp_side} | Opp Qty: {opp_qty} | Order Qty: {order_qty}")
                        if opp_qty >= int(order_qty):
                            can_afford = True
                            print(f"DEBUG: Local Netting Allowed | {api_side.upper()} {order_qty} vs {opp_side.upper()} {opp_qty}")

                if not can_afford:
                    if self._diag_log:
                        self._diag_log("ORDER", status="rejected_local_cash", cost=cost, cash=self._cash)
                    print(f"DEBUG: Local Reject | Cost: {cost:.2f} > Cash: {self._cash:.2f}")
                    # WARNING: Disabling local reject for LiveAdapter to avoid sync lag issues.
                    # return OrderResult(ok=False, filled=0, status="rejected_cash")
                    print("DEBUG: Bypassing local cash check (letting API decide)")
            except Exception as e:
                print(f"DEBUG: Pre-flight check error: {e}")
            # -----------------------------

            path = "/trade-api/v2/portfolio/orders"
            headers = create_headers(self.private_key, "POST", path)
            try:
                if self._diag_log:
                    self._diag_log(
                        "ORDER_SUBMIT",
                        tick_ts=current_time,
                        ticker=ticker,
                        orig_action=orig_action,
                        api_action=api_action,
                        api_side=api_side,
                        direction=api_action,
                        payload_side=api_side,
                        price=order_price,
                        qty=order_qty,
                        is_close=is_close,
                        cash=self._cash,
                        client_order_id=client_order_id,
                    )
                print(
                    f"DEBUG: ORDER_SUBMIT | {orig_action} is_close={is_close} -> {api_action.upper()} {api_side.upper()} "
                    f"{order_qty} @ {order_price} | cash={self._cash:.2f} | {ticker}"
                )
                resp = self._session.post(API_URL + path, headers=headers, json=payload)
                if resp.status_code == 201:
                    # Fix: Add to pending deductions immediately
                    if api_action == "buy":
                        calc_fee = calculate_convex_fee(order_price, int(order_qty))
                        cost = (int(order_qty) * (order_price / 100.0)) + calc_fee
                        self._pending_deductions.append({"time": time.time(), "cost": cost})
                        self._cash -= cost # Speculative local update
                        if self._diag_log:
                            self._diag_log("INFO", msg=f"Speculative cash deduction: -{cost:.2f} -> {self._cash:.2f}")

                    try:
                        data = resp.json() if resp.text else {}
                    except Exception:
                        data = {}
                    order_id = data.get("order").get("order_id")
                    if order_id and client_order_id:
                        self._client_id_by_order_id[order_id] = client_order_id
                    if ticker in self._open_orders_cache:
                        del self._open_orders_cache[ticker]
                    if self._diag_log:
                        self._diag_log("ORDER_ACK", order_id=order_id, status="open")
                    self.order_history.append(
                        {
                            "time": current_time,
                            "ticker": ticker,
                            "side": api_side,
                            "price": order_price,
                            "qty": order_qty,
                            "status": "accepted",
                            "filled": 0,
                            "order_id": None,
                            "client_order_id": client_order_id,
                            "order_time": current_time,
                        }
                    )
                    return OrderResult(ok=True, filled=0, status="resting")
                elif resp.status_code in (400, 403) and ("insufficient" in resp.text.lower() or "balance" in resp.text.lower()):
                    if self._diag_log:
                        self._diag_log("WARNING", msg=f"Order rejected (funds), attempting retry... {resp.text}")
                    
                    # 1. Sync State to get REAL cash
                    self._sync_state()
                    
                    # 2. Recalculate Max Quantity
                    if api_action == "buy":
                        p = order_price / 100.0
                        unit_cost = p + (0.07 * p * (1.0 - p))
                        unit_cost = max(unit_cost, 0.01) # Avoid div zero
                        
                        calc_max_qty = int(math.floor(self._cash / unit_cost))
                        
                        # 3. Aggressive Reduction: Try at least 1 less than before
                        # This handles case where our math is slightly off vs API
                        retry_qty = min(calc_max_qty, order_qty - 1)
                        
                        if retry_qty > 0:
                            print(f"DEBUG: RETRYING with Reduced Qty: {retry_qty} (was {order_qty}) | Cash: {self._cash:.2f}")
                            if self._diag_log:
                                self._diag_log("INFO", msg=f"Retrying with reduced qty: {retry_qty} (was {order_qty})")
                                
                            # Recursive retry with new qty
                            return _submit_order(
                                api_action=api_action,
                                api_side=api_side,
                                order_price=order_price,
                                order_qty=retry_qty,
                                is_close=is_close,
                                orig_action=orig_action
                            )
                        else:
                            print(f"DEBUG: Retry failed - Max Qty {retry_qty} too low.")

                msg = f"Place order failed: {resp.status_code} {resp.text}"
                print(f"DEBUG: API Error | {msg}")
                if self._diag_log:
                    self._diag_log(
                        "ORDER_REJECTED",
                        tick_ts=current_time,
                        ticker=ticker,
                        orig_action=orig_action,
                        action=api_action,
                        side=api_side,
                        price=order_price,
                        qty=order_qty,
                        msg=msg,
                    )
                return OrderResult(ok=False, filled=0, status="error")
            except Exception as e:
                if self._diag_log:
                    self._diag_log("ERROR", msg=f"Place order exception: {e}")
                return OrderResult(ok=False, filled=0, status="exception")

        # If engine marked this as a close, honor it explicitly (no open remainder).
        if order_is_close:
            if order.action == "BUY_NO":
                close_price = max(1, min(99, 100 - price))
                return _submit_order(
                    api_action="sell",
                    api_side="yes",
                    order_price=close_price,
                    order_qty=qty,
                    is_close=True,
                    orig_action=order.action,
                )
            if order.action == "BUY_YES":
                close_price = max(1, min(99, 100 - price))
                return _submit_order(
                    api_action="sell",
                    api_side="no",
                    order_price=close_price,
                    order_qty=qty,
                    is_close=True,
                    orig_action=order.action,
                )

        # Smart Order Splitting: close opposing inventory first, then open remainder.
        pos = self._positions.get(ticker, {})
        opp_side = "yes" if side == "no" else "no"
        opp_qty = int(pos.get(opp_side, 0))
        if opp_qty > 0:
            close_qty = min(qty, opp_qty)
            if close_qty > 0:
                close_side = opp_side
                close_price = 100 - price
            close_result = _submit_order(
                api_action="sell",
                api_side=close_side,
                order_price=close_price,
                order_qty=close_qty,
                is_close=True,
                orig_action=order.action,
            )
            if not close_result.ok:
                return close_result
            qty -= close_qty
            if qty <= 0:
                return close_result

        # Remainder (new exposure) uses the original buy side
        api_action = "buy"
        api_side = side
        return _submit_order(
            api_action=api_action,
            api_side=api_side,
            order_price=price,
            order_qty=qty,
            is_close=False,
            orig_action=order.action,
        )

    def amend_order(self, order_id: str, ticker: str, action: str, side: str, price: int, qty: int) -> bool:
        """
        Amend an existing order (Price/Qty).
        Matches signature called by engine.py.
        """
        path = f"/trade-api/v2/portfolio/orders/{order_id}"
        headers = create_headers(self.private_key, "PUT", path)
        
        payload = {
            "count": qty,
            "side": side,
        }
        
        # Set price field based on side
        if side == "yes":
            payload["yes_price"] = price
        elif side == "no":
            payload["no_price"] = price
        else:
            print(f"DEBUG: Amend failed - Unknown side {side}")
            return False
            
        try:
            resp = self._session.put(API_URL + path, headers=headers, json=payload)
            if resp.status_code == 200:
                # Success
                return True
            else:
                print(f"DEBUG: Amend failed: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            print(f"DEBUG: Amend exception: {e}")
            return False 

    def get_queue_position(self, order_id: str) -> int | None:
        if not order_id: return None
        path = f"/trade-api/v2/portfolio/orders/{order_id}/queue_position"
        headers = create_headers(self.private_key, "GET", path)
        try:
            resp = self._session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("queue_position")
        except Exception:
            pass
        return None
