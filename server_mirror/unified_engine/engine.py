from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass
class Order:
    action: str
    ticker: str
    qty: int
    price: float
    expiry: datetime | None
    source: str = "MM"
    time: datetime | None = None


class UnifiedEngine:
    def __init__(
        self,
        *,
        strategy,
        adapter,
        min_requote_interval: float = 2.0,
        diag_log=None,
        diag_every: int = 1,
        decision_log=None,
        trade_log=None,
    ):
        self.strategy = strategy
        self.adapter = adapter
        self.min_requote_interval = float(min_requote_interval)
        self.last_requote_time: dict[str, float] = {}
        self.diag_log = diag_log
        self.diag_every = max(int(diag_every), 1)
        self.decision_log = decision_log
        self.trade_log = trade_log
        self._decision_seq = 0
        self._trade_seq = 0

    def _emit_decision(
        self,
        *,
        tick_time: datetime,
        tick_seq: int | None,
        tick_source: str | None,
        tick_row: int | None,
        ticker: str,
        decision_type: str,
        orders: list[Order] | None,
        cash: float,
        pos_yes: int,
        pos_no: int,
        pending_yes: int,
        pending_no: int,
        market_state: dict | None,
    ) -> None:
        if not self.decision_log:
            return
        self._decision_seq += 1
        yes_ask = market_state.get("yes_ask") if market_state else None
        no_ask = market_state.get("no_ask") if market_state else None
        yes_bid = market_state.get("yes_bid") if market_state else None
        no_bid = market_state.get("no_bid") if market_state else None
        base = {
            "decision_id": self._decision_seq,
            "decision_time": datetime.now().isoformat(),
            "tick_time": tick_time.isoformat(),
            "tick_seq": tick_seq,
            "tick_source": tick_source,
            "tick_row": tick_row,
            "ticker": ticker,
            "decision_type": decision_type,
            "cash": cash,
            "pos_yes": pos_yes,
            "pos_no": pos_no,
            "pending_yes": pending_yes,
            "pending_no": pending_no,
            "yes_ask": yes_ask,
            "no_ask": no_ask,
            "yes_bid": yes_bid,
            "no_bid": no_bid,
        }
        if decision_type == "keep":
            self.decision_log(base)
            return
        if not orders:
            base["decision_type"] = "empty"
            self.decision_log(base)
            return
        for idx, order in enumerate(orders):
            row = dict(base)
            row.update(
                {
                    "order_index": idx,
                    "action": order.action,
                    "price": order.price,
                    "qty": order.qty,
                    "source": order.source,
                }
            )
            self.decision_log(row)

    def _emit_trade(
        self,
        *,
        tick_time: datetime,
        tick_seq: int | None,
        tick_source: str | None,
        tick_row: int | None,
        ticker: str,
        action: str,
        price: float,
        qty: int,
        cash: float,
        pos_yes: int,
        pos_no: int,
        pending_yes: int,
        pending_no: int,
        market_state: dict | None,
        order_source: str | None,
    ) -> None:
        if not self.trade_log:
            return
        self._trade_seq += 1
        yes_ask = market_state.get("yes_ask") if market_state else None
        no_ask = market_state.get("no_ask") if market_state else None
        yes_bid = market_state.get("yes_bid") if market_state else None
        no_bid = market_state.get("no_bid") if market_state else None
        self.trade_log(
            {
                "trade_id": self._trade_seq,
                "trade_time": datetime.now().isoformat(),
                "tick_time": tick_time.isoformat(),
                "tick_seq": tick_seq,
                "tick_source": tick_source,
                "tick_row": tick_row,
                "ticker": ticker,
                "action": action,
                "price": price,
                "qty": qty,
                "cash": cash,
                "pos_yes": pos_yes,
                "pos_no": pos_no,
                "pending_yes": pending_yes,
                "pending_no": pending_no,
                "yes_ask": yes_ask,
                "no_ask": no_ask,
                "yes_bid": yes_bid,
                "no_bid": no_bid,
                "order_source": order_source,
            }
        )

    def on_tick(
        self,
        *,
        ticker: str,
        market_state: dict,
        current_time: datetime,
        tick_seq: int | None = None,
        tick_source: str | None = None,
        tick_row: int | None = None,
    ) -> None:
        self.adapter.process_tick(ticker, market_state, current_time)

        open_orders = self.adapter.get_open_orders(ticker, market_state, current_time)
        active_orders = []
        pending_yes = 0
        pending_no = 0
        for o in open_orders:
            status = (o.get("status") or "").lower()
            remaining = int(o.get("remaining_count") or 0)
            if remaining <= 0:
                continue
            if status in ("executed", "cancelled", "canceled", "expired", "rejected"):
                continue
            side = (o.get("side") or "yes").lower()
            price = o.get("yes_price") if side == "yes" else o.get("no_price")
            if price is None:
                continue
            if side == "yes":
                pending_yes += remaining
            else:
                pending_no += remaining
            active_orders.append(
                {
                    "action": "BUY_YES" if side == "yes" else "BUY_NO",
                    "ticker": ticker,
                    "qty": remaining,
                    "price": price,
                    "source": "MM",
                    "id": o.get("order_id"),
                }
            )

        positions = self.adapter.get_positions()
        pos = positions.get(ticker, {"yes": 0, "no": 0})
        mm_inv = {
            "YES": int(pos.get("yes") or 0) + pending_yes,
            "NO": int(pos.get("no") or 0) + pending_no,
        }
        portfolios_inventories = {"MM": mm_inv}

        if self.min_requote_interval > 0:
            last_req = self.last_requote_time.get(ticker, 0.0)
            now = current_time.timestamp()
            if now - last_req < self.min_requote_interval:
                if "KXHIGHNY-26JAN09-B49.5" in ticker and "05:05:26" in str(current_time):
                    print(f"DEBUG: THROTTLED: {ticker} at {current_time}. Last req: {last_req}, Now: {now}, Diff: {now-last_req}")
                return

        cash = float(self.adapter.get_cash())
        desired_orders = self.strategy.on_market_update(
            ticker,
            market_state,
            current_time,
            portfolios_inventories,
            active_orders,
            cash,
        )

        if self.diag_log:
            if desired_orders is None:
                self.diag_log("DECISION", tick_ts=current_time, ticker=ticker, desired="keep")
            else:
                self.diag_log(
                    "DECISION",
                    tick_ts=current_time,
                    ticker=ticker,
                    desired=len(desired_orders),
                )

        pos_yes = int(pos.get("yes") or 0)
        pos_no = int(pos.get("no") or 0)
        if desired_orders is None:
            self._emit_decision(
                tick_time=current_time,
                tick_seq=tick_seq,
                tick_source=tick_source,
                tick_row=tick_row,
                ticker=ticker,
                decision_type="keep",
                orders=None,
                cash=cash,
                pos_yes=pos_yes,
                pos_no=pos_no,
                pending_yes=pending_yes,
                pending_no=pending_no,
                market_state=market_state,
            )
            return

        self.last_requote_time[ticker] = current_time.timestamp()

        desired = [Order(**o) if isinstance(o, dict) else o for o in desired_orders]
        self._emit_decision(
            tick_time=current_time,
            tick_seq=tick_seq,
            tick_source=tick_source,
            tick_row=tick_row,
            ticker=ticker,
            decision_type="desired",
            orders=desired,
            cash=cash,
            pos_yes=pos_yes,
            pos_no=pos_no,
            pending_yes=pending_yes,
            pending_no=pending_no,
            market_state=market_state,
        )

        kept_ids = set()
        unsatisfied: list[Order] = []
        for want in desired:
            matched = False
            for existing in active_orders:
                if existing["id"] in kept_ids:
                    continue
                if (
                    existing["action"] == want.action
                    and existing["price"] == want.price
                    and existing["qty"] >= want.qty
                ):
                    kept_ids.add(existing["id"])
                    matched = True
                    break
            if not matched:
                unsatisfied.append(want)

        for existing in active_orders:
            if existing["id"] not in kept_ids:
                self.adapter.cancel_order(existing["id"])

        for order in unsatisfied:
            self._emit_trade(
                tick_time=current_time,
                tick_seq=tick_seq,
                tick_source=tick_source,
                tick_row=tick_row,
                ticker=ticker,
                action=order.action,
                price=order.price,
                qty=order.qty,
                cash=cash,
                pos_yes=pos_yes,
                pos_no=pos_no,
                pending_yes=pending_yes,
                pending_no=pending_no,
                market_state=market_state,
                order_source=getattr(order, "source", None),
            )
            self.adapter.place_order(order, market_state, current_time)

    def run(self, ticks: Iterable[dict]) -> None:
        count = 0
        for tick in ticks:
            count += 1
            if self.diag_log and (count % self.diag_every == 0):
                self.diag_log("TICK_IN", tick_ts=tick["time"], ticker=tick["ticker"])
            self.on_tick(
                ticker=tick["ticker"],
                market_state=tick["market_state"],
                current_time=tick["time"],
                tick_seq=tick.get("seq"),
                tick_source=tick.get("source_file"),
                tick_row=tick.get("source_row"),
            )
