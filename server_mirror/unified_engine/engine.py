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
        amend_price_tolerance: float = 0.0,
        amend_qty_tolerance: int = 0,
        diag_log=None,
        diag_every: int = 1,
        decision_log=None,
        trade_log=None,
    ):
        self.strategy = strategy
        self.adapter = adapter
        self.min_requote_interval = float(min_requote_interval)
        self.amend_price_tolerance = float(amend_price_tolerance)
        self.amend_qty_tolerance = int(amend_qty_tolerance)
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
            action = (o.get("action") or "buy").lower()
            price = o.get("yes_price") if side == "yes" else o.get("no_price")
            if price is None:
                continue
            if side == "yes":
                pending_yes += remaining
            else:
                pending_no += remaining
            
            # Map API orders to Strategy Actions
            # Strategy uses BUY_YES / BUY_NO
            # API Buy YES -> BUY_YES
            # API Buy NO  -> BUY_NO
            # API Sell YES -> BUY_NO (Equivalent)
            # API Sell NO  -> BUY_YES (Equivalent)
            
            mapped_action = "BUY_YES"
            mapped_price = price
            
            if action == "buy":
                if side == "no":
                    mapped_action = "BUY_NO"
            elif action == "sell":
                if side == "yes":
                    mapped_action = "BUY_NO"
                    # Sell YES at X means Buy NO at 100-X
                    # API returns yes_price for side=yes.
                    # We need to convert to no_price for strategy matching.
                    if price is not None:
                        mapped_price = 100 - price
                elif side == "no":
                    # Sell NO at X means Buy YES at 100-X
                    mapped_action = "BUY_YES"
                    if price is not None:
                        mapped_price = 100 - price
            
            active_orders.append(
                {
                    "action": mapped_action,
                    "ticker": ticker,
                    "qty": remaining,
                    "price": mapped_price,
                    "source": "MM",
                    "id": o.get("order_id"),
                    "api_action": action,
                    "api_side": side,
                }
            )

        positions = self.adapter.get_positions()
        pos = positions.get(ticker, {"yes": 0, "no": 0})
        mm_inv = {
            "yes": int(pos.get("yes") or 0) + pending_yes,
            "no": int(pos.get("no") or 0) + pending_no,
        }
        portfolios_inventories = {ticker: mm_inv}

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

        desired = []
        for o in desired_orders:
            if isinstance(o, dict):
                payload = dict(o)
                payload.pop("decision_qty", None)
                desired.append(Order(**payload))
            else:
                desired.append(o)
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
                
                # Check for Match (Action must match)
                if existing["action"] == want.action:
                    # 0. Close-enough Match (within tolerance)
                    try:
                        price_diff = abs(float(existing["price"]) - float(want.price))
                    except Exception:
                        price_diff = float("inf")
                    try:
                        qty_diff = abs(int(existing["qty"]) - int(want.qty))
                    except Exception:
                        qty_diff = 10**9

                    if price_diff <= self.amend_price_tolerance and qty_diff <= self.amend_qty_tolerance:
                        kept_ids.add(existing["id"])
                        matched = True
                        break

                    # 1. Perfect Match
                    if existing["price"] == want.price and existing["qty"] == want.qty:
                        kept_ids.add(existing["id"])
                        matched = True
                        # print(f"DEBUG: Perfect Match {existing['id']} | {want.action} {want.price}")
                        break
                    
                    # 2. Amendable Match (Same Action, Different Price/Qty)
                    if hasattr(self.adapter, "amend_order"):
                        raw_price = want.price
                        if existing["api_action"] == "sell":
                             if existing["action"] == "BUY_NO" and existing["api_side"] == "yes":
                                 raw_price = 100 - want.price
                             elif existing["action"] == "BUY_YES" and existing["api_side"] == "no":
                                 raw_price = 100 - want.price
                        
                        print(f"DEBUG: Amending {existing['id']} | Want: {want.price} (Raw: {raw_price}) | Have: {existing['price']}")
                        success = self.adapter.amend_order(
                            order_id=existing["id"],
                            ticker=ticker,
                            action=existing["api_action"],
                            side=existing["api_side"],
                            price=raw_price,
                            qty=want.qty
                        )
                        if success:
                            kept_ids.add(existing["id"])
                            matched = True
                            break
                        else:
                            print(f"DEBUG: Amend Failed for {existing['id']}")
            
            if not matched:
                print(f"DEBUG: No Match Found for {want.action} {want.price} {want.qty}")
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
