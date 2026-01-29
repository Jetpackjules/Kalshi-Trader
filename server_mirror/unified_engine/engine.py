from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Iterable
import math


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
    LOCAL_TZ = ZoneInfo("America/Los_Angeles")

    def __init__(
        self,
        *,
        strategy,
        adapter,
        min_requote_interval: float = 2.0,
        amend_price_tolerance: float = 0.0,
        amend_qty_tolerance: int = 0,
        min_quote_lifetime_s: float = 2.0,
        reprice_min_cents: int = 2,
        resize_min_abs: int = 2,
        resize_min_rel: float = 0.20,
        max_actions_per_minute: int = 6,
        trade_live_window_s: float = 0.0,
        allow_warmup_old_ticks: bool = False,
        max_order_age_s: float = 0.0,
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
        self.min_quote_lifetime_s = float(min_quote_lifetime_s)
        self.reprice_min_cents = int(reprice_min_cents)
        self.resize_min_abs = int(resize_min_abs)
        self.resize_min_rel = float(resize_min_rel)
        self.max_actions_per_minute = int(max_actions_per_minute)
        self.trade_live_window_s = float(trade_live_window_s)
        self.allow_warmup_old_ticks = bool(allow_warmup_old_ticks)
        self.max_order_age_s = float(max_order_age_s)
        self.last_requote_time: dict[str, float] = {}
        self._action_times: dict[str, list[float]] = {}
        self._last_open_reject: dict[str, float] = {}
        self.open_reject_cooldown_s = 15.0
        self.diag_log = diag_log
        self.diag_every = max(int(diag_every), 1)
        self.decision_log = decision_log
        self.trade_log = trade_log
        self._decision_seq = 0
        self._trade_seq = 0
        self._stale_seq = 0
        self.metric_interval_s = 30.0
        self._last_metric_ts: dict[str, float] = {}

    def _now_local_naive(self) -> datetime:
        return datetime.now(self.LOCAL_TZ).replace(tzinfo=None)

    def _ensure_local_naive(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(self.LOCAL_TZ).replace(tzinfo=None)

    def _parse_time(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
        return self._ensure_local_naive(parsed)

    def _fee_cents_approx(self, price_cents: float) -> float:
        p = float(price_cents) / 100.0
        return 7.0 * p * (1.0 - p)

    def _can_afford_open(self, order: Order, cash: float, buffer_dollars: float = 0.50) -> bool:
        price_cents = float(order.price)
        fee_cents = self._fee_cents_approx(price_cents)
        est_cost = (order.qty * (price_cents + fee_cents)) / 100.0
        return cash >= (est_cost + buffer_dollars)

    def _is_close_action(self, action: str, net_inv: int) -> bool:
        if net_inv > 0 and action == "BUY_NO":
            return True
        if net_inv < 0 and action == "BUY_YES":
            return True
        return False

    def _can_take_action(self, ticker: str, now_ts: float) -> bool:
        if self.max_actions_per_minute <= 0:
            return True
        window = 60.0
        times = self._action_times.get(ticker, [])
        cutoff = now_ts - window
        times = [t for t in times if t >= cutoff]
        if len(times) >= self.max_actions_per_minute:
            self._action_times[ticker] = times
            return False
        self._action_times[ticker] = times
        return True

    def _record_action(self, ticker: str, now_ts: float) -> None:
        if self.max_actions_per_minute <= 0:
            return
        times = self._action_times.get(ticker, [])
        times.append(now_ts)
        self._action_times[ticker] = times

    def _recent_open_reject(self, ticker: str, now_ts: float) -> bool:
        last = self._last_open_reject.get(ticker)
        if last is None:
            return False
        return (now_ts - last) < self.open_reject_cooldown_s

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
            "decision_time": self._now_local_naive().isoformat(),
            "tick_time": self._ensure_local_naive(tick_time).isoformat(),
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
                "trade_time": self._now_local_naive().isoformat(),
                "tick_time": self._ensure_local_naive(tick_time).isoformat(),
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
        current_time = self._ensure_local_naive(current_time) or current_time
        self.adapter.process_tick(ticker, market_state, current_time)

        if self.trade_live_window_s > 0:
            lag_s = (self._now_local_naive() - current_time).total_seconds()
            if lag_s > self.trade_live_window_s:
                self._stale_seq += 1
                if self.diag_log and (self._stale_seq % self.diag_every == 0):
                    self.diag_log(
                        "STALE_TICK",
                        tick_ts=current_time,
                        ticker=ticker,
                        lag_s=round(lag_s, 3),
                        window_s=self.trade_live_window_s,
                        source=tick_source,
                        row=tick_row,
                    )
                if not self.allow_warmup_old_ticks:
                    return
                try:
                    self.strategy.on_market_update(
                        ticker,
                        market_state,
                        current_time,
                        {ticker: {"yes": 0, "no": 0}},
                        [],
                        0.0,
                    )
                except Exception:
                    pass
                return

        open_orders = self.adapter.get_open_orders(ticker, market_state, current_time)
        active_orders = []
        pending_yes = 0
        pending_no = 0
        now_wall = self._now_local_naive()
        for o in open_orders:
            status = (o.get("status") or "").lower()
            remaining = int(o.get("remaining_count") or 0)
            if remaining <= 0:
                continue
            if status in ("executed", "cancelled", "canceled", "expired", "rejected"):
                continue
            if self.max_order_age_s > 0:
                created = o.get("created_time")
                if created:
                    try:
                        created_ts = self._parse_time(str(created))
                        if created_ts is not None:
                            age_s = (now_wall - created_ts).total_seconds()
                        else:
                            age_s = None
                        if age_s is not None and age_s > self.max_order_age_s:
                            self.adapter.cancel_order(o.get("order_id"))
                            self._record_action(ticker, current_time.timestamp())
                            if self.diag_log:
                                self.diag_log(
                                    "STALE_ORDER_CANCEL",
                                    tick_ts=current_time,
                                    ticker=ticker,
                                    order_id=o.get("order_id"),
                                    age_s=round(age_s, 1),
                                )
                            continue
                    except Exception:
                        pass
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
                    "created_time": o.get("created_time"),
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

        # Periodic per-ticker metric line to make audit/debugging easy.
        if self.diag_log:
            now_ts = current_time.timestamp()
            last = self._last_metric_ts.get(ticker, 0.0)
            if now_ts - last >= self.metric_interval_s:
                # Keep the sliding window consistent with _can_take_action().
                times = self._action_times.get(ticker, [])
                cutoff = now_ts - 60.0
                actions_last_60s = len([t for t in times if t >= cutoff])
                buy_orders = sum(1 for o in open_orders if (o.get("action") or "").lower() == "buy")
                sell_orders = sum(1 for o in open_orders if (o.get("action") or "").lower() == "sell")
                self.diag_log(
                    "METRIC",
                    tick_ts=current_time,
                    ticker=ticker,
                    cash=round(cash, 2),
                    pos_yes=int(pos.get("yes") or 0),
                    pos_no=int(pos.get("no") or 0),
                    pending_yes=pending_yes,
                    pending_no=pending_no,
                    net_inv=int(mm_inv.get("yes") or 0) - int(mm_inv.get("no") or 0),
                    actions_last_60s=actions_last_60s,
                    open_orders=len(open_orders),
                    buy_orders=buy_orders,
                    sell_orders=sell_orders,
                    recent_open_reject=self._recent_open_reject(ticker, now_ts),
                )
                self._last_metric_ts[ticker] = now_ts

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
                
                is_close_existing = existing.get("api_action") == "sell"
                created_at = self._parse_time(existing.get("created_time"))
                order_age_s = None
                if created_at:
                    try:
                        order_age_s = (current_time - created_at).total_seconds()
                    except Exception:
                        order_age_s = None

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

                    # Minimum quote lifetime (skip churn on very fresh orders).
                    if (
                        not is_close_existing
                        and self.min_quote_lifetime_s > 0
                        and order_age_s is not None
                        and order_age_s < self.min_quote_lifetime_s
                    ):
                        kept_ids.add(existing["id"])
                        matched = True
                        break

                    # Reprice/resize hygiene: require meaningful change.
                    min_price_move = 1 if is_close_existing else self.reprice_min_cents
                    min_qty_change = max(
                        1 if is_close_existing else self.resize_min_abs,
                        int(math.ceil((self.resize_min_rel if not is_close_existing else 0.10) * max(1, int(existing["qty"])))),
                    )
                    if price_diff < min_price_move and qty_diff < min_qty_change:
                        kept_ids.add(existing["id"])
                        matched = True
                        break

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
                        if not self._can_take_action(ticker, current_time.timestamp()):
                            kept_ids.add(existing["id"])
                            matched = True
                            break
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
                        self._record_action(ticker, current_time.timestamp())
                        if success:
                            kept_ids.add(existing["id"])
                            matched = True
                            break
                        else:
                            print(f"DEBUG: Amend Failed for {existing['id']}")
            
            if not matched:
                print(f"DEBUG: No Match Found for {want.action} {want.price} {want.qty}")
                unsatisfied.append(want)

        # Keep close-only orders live until flat, even if strategy returns empty.
        # Use effective inventory (including pending) so closes aren't misclassified.
        net_inv = (pos_yes + pending_yes) - (pos_no + pending_no)
        close_action = None
        if net_inv > 0:
            close_action = "BUY_NO"   # close YES via SELL YES
        elif net_inv < 0:
            close_action = "BUY_YES"  # close NO via SELL NO

        for existing in active_orders:
            if existing["id"] in kept_ids:
                continue
            if close_action and existing.get("action") == close_action:
                # Keep the exit order alive while inventory remains.
                continue
            created_at = self._parse_time(existing.get("created_time"))
            if (
                self.min_quote_lifetime_s > 0
                and created_at is not None
                and (current_time - created_at).total_seconds() < self.min_quote_lifetime_s
            ):
                continue
            if not self._can_take_action(ticker, current_time.timestamp()):
                continue
            self.adapter.cancel_order(existing["id"])
            self._record_action(ticker, current_time.timestamp())

        for order in unsatisfied:
            is_close = self._is_close_action(order.action, net_inv)
            now_ts = current_time.timestamp()
            if not is_close and self._recent_open_reject(ticker, now_ts):
                if self.diag_log:
                    self.diag_log(
                        "ORDER_SKIP",
                        tick_ts=current_time,
                        ticker=ticker,
                        action=order.action,
                        price=order.price,
                        qty=order.qty,
                        reason="open_reject_cooldown",
                        cash=cash,
                    )
                continue
            if not is_close and not self._can_afford_open(order, cash):
                if self.diag_log:
                    self.diag_log(
                        "ORDER_SKIP",
                        tick_ts=current_time,
                        ticker=ticker,
                        action=order.action,
                        price=order.price,
                        qty=order.qty,
                        reason="insufficient_cash_preflight",
                        cash=cash,
                    )
                continue
            if not self._can_take_action(ticker, now_ts):
                continue
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
            result = self.adapter.place_order(order, market_state, current_time)
            self._record_action(ticker, now_ts)
            if not is_close and (not result or not getattr(result, "ok", False)):
                self._last_open_reject[ticker] = now_ts

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
