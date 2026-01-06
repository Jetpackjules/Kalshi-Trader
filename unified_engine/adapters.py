from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import csv
import json
import os

import math


def calculate_convex_fee(price: float, qty: int) -> float:
    p = price / 100.0
    raw_fee = 0.07 * qty * p * (1 - p)
    return math.ceil(raw_fee * 100) / 100.0


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
    def __init__(self, *, initial_cash: float = 0.0, diag_log=None, out_dir: str | None = None):
        self.cash = float(initial_cash)
        self.positions: dict[str, dict[str, Any]] = {}
        self.open_orders: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self.order_history: list[dict[str, Any]] = []
        self._order_id = 0
        self._diag_log = diag_log
        self._out_dir = out_dir
        self._trades_path = None
        self._orders_path = None
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            self._trades_path = os.path.join(out_dir, "unified_trades.csv")
            self._orders_path = os.path.join(out_dir, "unified_orders.csv")

    def _append_trade_row(self, trade: dict[str, Any]) -> None:
        if not self._trades_path:
            return
        file_exists = os.path.isfile(self._trades_path)
        with open(self._trades_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["time", "action", "ticker", "price", "qty", "fee", "cost", "source"])
            writer.writerow([
                trade["time"],
                trade["action"],
                trade["ticker"],
                trade["price"],
                trade["qty"],
                trade["fee"],
                trade["cost"],
                trade["source"],
            ])

    def _append_order_row(self, order: dict[str, Any]) -> None:
        if not self._orders_path:
            return
        file_exists = os.path.isfile(self._orders_path)
        with open(self._orders_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["time", "ticker", "side", "price", "qty", "status", "filled"])
            writer.writerow([
                order["time"],
                order["ticker"],
                order["side"],
                order["price"],
                order["qty"],
                order["status"],
                order.get("filled", 0),
            ])


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
            self._append_order_row(self.order_history[-1])
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
        self._append_order_row(self.order_history[-1])
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

        trade = {
            "time": current_time,
            "action": "BUY_YES" if side == "yes" else "BUY_NO",
            "ticker": ticker,
            "price": price,
            "qty": qty,
            "fee": fee,
            "cost": cost,
            "source": "SIM",
        }
        self.trades.append(trade)
        self._append_trade_row(trade)
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
