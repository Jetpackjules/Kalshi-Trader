from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


class SimAdapter(BaseAdapter):
    def __init__(self, *, initial_cash: float = 0.0, diag_log=None):
        self.cash = float(initial_cash)
        self.positions: dict[str, dict[str, Any]] = {}
        self.open_orders: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self.order_history: list[dict[str, Any]] = []
        self._order_id = 0
        self._diag_log = diag_log

    def _next_id(self) -> str:
        self._order_id += 1
        return f"SIM_{self._order_id}"

    def process_tick(self, ticker: str, market_state: dict, current_time: datetime) -> None:
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

        new_order = {
            "order_id": order_id,
            "ticker": order.ticker,
            "side": side,
            "yes_price": price if side == "yes" else None,
            "no_price": price if side == "no" else None,
            "remaining_count": qty,
            "status": "open",
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
                }
            )
            return OrderResult(ok=True, filled=filled, status="executed")

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
            }
        )
        return OrderResult(ok=True, filled=0, status="resting")

    def _maybe_fill(self, order: dict, market_state: dict, current_time: datetime) -> int:
        side = order["side"]
        price = float(order["yes_price"] if side == "yes" else order["no_price"])
        qty = int(order["remaining_count"])
        if qty <= 0:
            return 0

        ask = market_state.get("yes_ask") if side == "yes" else market_state.get("no_ask")
        if ask is None:
            return 0
        if price < float(ask):
            return 0

        self._fill_order(order, price=float(ask), qty=qty, current_time=current_time)
        return qty

    def _fill_order(self, order: dict, *, price: float, qty: int, current_time: datetime) -> None:
        ticker = order["ticker"]
        side = order["side"]
        fee = calculate_convex_fee(price, qty)
        cost = qty * (price / 100.0) + fee
        if self.cash < cost:
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
            return

        pos = self.positions.setdefault(ticker, {"yes": 0, "no": 0, "cost": 0.0})
        if side == "yes":
            pos["yes"] += qty
        else:
            pos["no"] += qty
        pos["cost"] += cost
        self.cash -= cost

        order["remaining_count"] = 0
        order["status"] = "executed"

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


class LiveAdapter(BaseAdapter):
    def __init__(self, key_path: str, diag_log=None):
        self._diag_log = diag_log
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
        self._orders_cache_ttl = 2.0
        
        # Track session trades
        self.trades = []
        self.order_history = []

        # Initial Sync
        self._sync_state()

    def _sync_state(self):
        try:
            # 1. Balance
            path = "/trade-api/v2/portfolio/balance"
            headers = create_headers(self.private_key, "GET", path)
            resp = self._session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                self._cash = float(data.get("balance", 0.0)) / 100.0 # API returns cents
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



            self._last_sync_time = time.time()
        except Exception as e:
            if self._diag_log:
                self._diag_log("ERROR", msg=f"Sync failed: {e}")

    def get_cash(self) -> float:
        if time.time() - self._last_sync_time > self._sync_interval:
            self._sync_state()
        return self._cash

    def get_portfolio_value(self) -> float:
        if time.time() - self._last_sync_time > self._sync_interval:
            self._sync_state()
        return self._portfolio_value

    def get_positions(self) -> dict[str, dict[str, Any]]:
        if time.time() - self._last_sync_time > self._sync_interval:
            self._sync_state()
        return self._positions

    def get_open_orders(self, ticker: str, market_state: dict, current_time: datetime) -> list[dict]:
        # Check cache
        cached = self._open_orders_cache.get(ticker)
        if cached:
            ts, orders = cached
            if time.time() - ts < self._orders_cache_ttl:
                return orders

        # Fetch from API
        path = f"/trade-api/v2/portfolio/orders?ticker={ticker}&status=open"
        headers = create_headers(self.private_key, "GET", path)
        try:
            resp = self._session.get(API_URL + path, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                orders = []
                for o in data.get("orders", []):
                    # Map API order to Engine order format
                    # API: { "order_id": "...", "ticker": "...", "side": "yes", "yes_price": 50, "remaining_count": 10, ... }
                    orders.append({
                        "order_id": o.get("order_id"),
                        "ticker": o.get("ticker"),
                        "side": o.get("side"),
                        "yes_price": o.get("yes_price"), # or price
                        "no_price": o.get("no_price"),
                        "remaining_count": o.get("remaining_count"),
                        "status": o.get("status")
                    })
                self._open_orders_cache[ticker] = (time.time(), orders)
                return orders
        except Exception as e:
            if self._diag_log:
                self._diag_log("ERROR", msg=f"Get orders failed: {e}")
        
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

    def place_order(self, order, market_state: dict, current_time: datetime) -> OrderResult:
        # order is an object or dict from Engine
        # Engine passes 'Order' object or dict.
        # Engine.py: self.adapter.place_order(order, ...)
        # order has .action, .ticker, .qty, .price, .side (derived)
        
        side = "yes" if order.action == "BUY_YES" else "no"
        price = int(order.price) # API expects integer cents? Or not?
        # Kalshi V2 usually expects integer cents for limit orders?
        # Let's assume integer cents.
        
        # API Payload
        payload = {
            "action": "buy", # We only buy
            "ticker": order.ticker,
            "count": int(order.qty),
            "type": "limit",
            "side": side,
            "yes_price": price if side == "yes" else None,
            "no_price": price if side == "no" else None,
            # "expiration_ts": ... # Optional
        }
        # Clean None values
        payload = {k: v for k, v in payload.items() if v is not None}
        
        path = "/trade-api/v2/portfolio/orders"
        headers = create_headers(self.private_key, "POST", path)
        try:
            resp = self._session.post(API_URL + path, headers=headers, json=payload)
            if resp.status_code == 201:
                data = resp.json()
                order_id = data.get("order_id")
                # Invalidate cache
                if order.ticker in self._open_orders_cache:
                    del self._open_orders_cache[order.ticker]
                
                # --- LEGACY BEHAVIOR: Log Order as Trade ---
                # The user requested to match live_trader_v4 behavior where placed orders
                # are logged to trades.csv immediately, regardless of fill status.
                # This treats "trades.csv" as an "Order Log".
                try:
                    fee = calculate_convex_fee(price, int(order.qty))
                    cost = (int(order.qty) * (price / 100.0)) + fee
                    
                    trade_record = {
                        "time": datetime.now(), # Wall clock time of placement
                        "action": order.action,
                        "ticker": order.ticker,
                        "price": price,
                        "qty": int(order.qty),
                        "fee": fee,
                        "cost": cost,
                        "source": order.source,
                        "order_id": order_id # Extra metadata
                    }
                    self.trades.append(trade_record)
                except Exception as e:
                    if self._diag_log:
                        self._diag_log("ERROR", msg=f"Failed to log trade: {e}")
                # -------------------------------------------

                return OrderResult(ok=True, filled=0, status="resting") # Assume resting for limit
            else:
                if self._diag_log:
                    self._diag_log("ERROR", msg=f"Place order failed: {resp.text}")
                return OrderResult(ok=False, filled=0, status="error")
        except Exception as e:
            if self._diag_log:
                self._diag_log("ERROR", msg=f"Place order exception: {e}")
            return OrderResult(ok=False, filled=0, status="exception")
