from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Iterable
import math
import hashlib
import re


@dataclass
class Order:
    action: str
    ticker: str
    qty: int
    price: float
    expiry: datetime | None
    source: str = "MM"
    time: datetime | None = None
    client_order_id: str | None = None
    is_close: bool | None = None


class UnifiedEngine:
    LOCAL_TZ = ZoneInfo("America/Los_Angeles")

    def __init__(
        self,
        *,
        strategy,
        adapter,
        min_requote_interval: float = 0.0,
        amend_price_tolerance: float = 0.0,
        amend_qty_tolerance: int = 0,
        min_quote_lifetime_s: float = 0.0,
        reprice_min_cents: int = 0,
        resize_min_abs: int = 0,
        resize_min_rel: float = 0.0,
        max_actions_per_minute: int = 0,
        trade_live_window_s: float = 0.0,
        allow_warmup_old_ticks: bool = False,
        max_order_age_s: float = 0.0,
        open_reject_cooldown_s: float = 0.0,
        enforce_cash_preflight: bool = False,
        cash_preflight_buffer_dollars: float = 0.50,
        cancel_stale_unmatched: bool = False,
        diag_log=None,
        diag_every: int = 1,
        decision_log=None,
        trade_log=None,
        order_event_log=None,
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
        self.open_reject_cooldown_s = max(0.0, float(open_reject_cooldown_s))
        self.enforce_cash_preflight = bool(enforce_cash_preflight)
        self.cash_preflight_buffer_dollars = max(0.0, float(cash_preflight_buffer_dollars))
        self.cancel_stale_unmatched = bool(cancel_stale_unmatched)
        self.last_requote_time: dict[str, float] = {}
        self._action_times: dict[str, list[float]] = {}
        self._last_open_reject: dict[str, float] = {}
        self.diag_log = diag_log
        self.diag_every = max(int(diag_every), 1)
        self.decision_log = decision_log
        self.trade_log = trade_log
        self.order_event_log = order_event_log
        self._decision_seq = 0
        self._trade_seq = 0
        self._stale_seq = 0
        self._order_event_seq = 0
        self._order_seq = 0
        self._run_id = datetime.now(self.LOCAL_TZ).strftime("%Y%m%d_%H%M%S")
        self.metric_interval_s = 30.0
        self._last_metric_ts: dict[str, float] = {}
        self.trading_enabled = True # Default to True

    def set_trading_enabled(self, enabled: bool) -> None:
        if self.trading_enabled != enabled:
            print(f"DEBUG: Trading Enabled changed to {enabled}")
        self.trading_enabled = bool(enabled)

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

    def _is_close_action(
        self,
        action: str,
        pos_yes: int,
        pos_no: int,
        pending_yes: int = 0,
        pending_no: int = 0,
    ) -> bool:
        eff_yes = int(pos_yes or 0) + int(pending_yes or 0)
        eff_no = int(pos_no or 0) + int(pending_no or 0)
        if action == "BUY_NO":
            return eff_yes > 0
        if action == "BUY_YES":
            return eff_no > 0
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

    def _next_client_order_id(self, *, ticker: str, action: str, source: str | None, now: datetime) -> str:
        """Generate a short, API-safe client_order_id (alnum/_/- only, <=64 chars)."""
        self._order_seq += 1
        ts_ms = int(now.timestamp() * 1000)

        safe_source = (source or "MM")
        safe_source = re.sub(r"[^A-Za-z0-9_-]", "_", safe_source)
        safe_ticker = re.sub(r"[^A-Za-z0-9_-]", "_", ticker)
        safe_action = re.sub(r"[^A-Za-z0-9_-]", "_", action)

        core = f"{self._run_id}-{safe_ticker}-{safe_source}-{safe_action}-{ts_ms}-{self._order_seq}"
        core = re.sub(r"[^A-Za-z0-9_-]", "_", core)

        if len(core) > 64:
            digest = hashlib.sha1(core.encode("utf-8")).hexdigest()[:10]
            short_run = re.sub(r"[^A-Za-z0-9]", "", self._run_id)[:8]
            short_ticker = safe_ticker[-10:]
            short_action = safe_action[:4]
            core = f"{short_run}-{short_ticker}-{short_action}-{ts_ms % 100000000}-{self._order_seq}-{digest}"
            core = re.sub(r"[^A-Za-z0-9_-]", "_", core)

        return core[:64]

    def _emit_order_event(
        self,
        *,
        event: str,
        tick_time: datetime,
        ticker: str,
        action: str | None,
        price: float | None,
        qty: int | None,
        is_close: bool | None,
        reason: str | None = None,
        cash: float | None = None,
        pos_yes: int | None = None,
        pos_no: int | None = None,
        pending_yes: int | None = None,
        pending_no: int | None = None,
        market_state: dict | None = None,
        client_order_id: str | None = None,
        order_id: str | None = None,
        api_action: str | None = None,
        api_side: str | None = None,
    ) -> None:
        if not self.order_event_log:
            return
        self._order_event_seq += 1
        yes_ask = market_state.get("yes_ask") if market_state else None
        no_ask = market_state.get("no_ask") if market_state else None
        yes_bid = market_state.get("yes_bid") if market_state else None
        no_bid = market_state.get("no_bid") if market_state else None
        row = {
            "event_id": self._order_event_seq,
            "event_time": self._now_local_naive().isoformat(),
            "tick_time": self._ensure_local_naive(tick_time).isoformat(),
            "event": event,
            "ticker": ticker,
            "action": action,
            "price": price,
            "qty": qty,
            "is_close": is_close,
            "reason": reason,
            "cash": cash,
            "pos_yes": pos_yes,
            "pos_no": pos_no,
            "pending_yes": pending_yes,
            "pending_no": pending_no,
            "yes_ask": yes_ask,
            "no_ask": no_ask,
            "yes_bid": yes_bid,
            "no_bid": no_bid,
            "client_order_id": client_order_id,
            "order_id": order_id,
            "api_action": api_action,
            "api_side": api_side,
        }
        self.order_event_log(row)

    def _recent_open_reject(self, ticker: str, now_ts: float) -> bool:
        if self.open_reject_cooldown_s <= 0:
            return False
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
        
        # Build comprehensive inventory for strategy visibility
        # Start with all positions from adapter
        portfolios_inventories = {}
        for tkr, pos in positions.items():
            portfolios_inventories[tkr] = {
                "yes": int(pos.get("yes") or 0),
                "no": int(pos.get("no") or 0),
            }
        
        # Overlay current ticker's pending orders to ensure atomic updates
        # (Other tickers might have pending too but we only process one stream here)
        mm_inv = {
            "yes": int(positions.get(ticker, {}).get("yes") or 0) + pending_yes,
            "no": int(positions.get(ticker, {}).get("no") or 0) + pending_no,
        }
        portfolios_inventories[ticker] = mm_inv

        if self.min_requote_interval > 0:
            last_req = self.last_requote_time.get(ticker, 0.0)
            now = current_time.timestamp()
            if now - last_req < self.min_requote_interval:
                if "KXHIGHNY-26JAN09-B49.5" in ticker and "05:05:26" in str(current_time):
                    print(f"DEBUG: THROTTLED: {ticker} at {current_time}. Last req: {last_req}, Now: {now}, Diff: {now-last_req}")
                return

        cash = float(self.adapter.get_cash())
        if not self.trading_enabled:
            # Kill Switch Active: Skip strategy logic
            if self.diag_log:
                # Throttle this log? 
                pass
            
            # Still update adapter but send NO orders?
            # Actually, we should just return early or pass empty desired orders.
            # Passing empty desired orders ensures valid cancellation of *other* orders if needed?
            # No, if we want to FREEZE, we should do nothing.
            # If we want to "Stop Trading", usually implies "Cancel All" or "Stop Placing New".
            # Let's assume "Stop Placing New". Existing orders might need management?
            # Safer to just return "keep" (None) to engine logic?
            # If we return None, engine does "keep".
            
            desired_orders = None
            if self.diag_log and (self._stale_seq % self.diag_every == 0): 
                 self.diag_log("DECISION", tick_ts=current_time, ticker=ticker, desired="stopped")
        else:
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
                pos = portfolios_inventories.get(ticker, {})
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
            gate_reason = getattr(self.strategy, "last_gate_reason", None)
            gate_detail = getattr(self.strategy, "last_gate_detail", None)
            if desired_orders is None:
                self.diag_log(
                    "DECISION",
                    tick_ts=current_time,
                    ticker=ticker,
                    desired="keep",
                    gate=gate_reason,
                    gate_detail=gate_detail,
                )
            else:
                self.diag_log(
                    "DECISION",
                    tick_ts=current_time,
                    ticker=ticker,
                    desired=len(desired_orders),
                    gate=gate_reason,
                    gate_detail=gate_detail,
                )

        pos = portfolios_inventories.get(ticker, {})
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
                    min_price_move = max(0, int(self.reprice_min_cents))
                    min_qty_change = max(
                        max(0, int(self.resize_min_abs)),
                        int(math.ceil(max(0.0, float(self.resize_min_rel)) * max(1, int(existing["qty"])))),
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
                            self._emit_order_event(
                                event="AMEND_SKIP",
                                tick_time=current_time,
                                ticker=ticker,
                                action=want.action,
                                price=want.price,
                                qty=want.qty,
                                is_close=is_close_existing,
                                reason="action_budget",
                                cash=cash,
                                pos_yes=pos_yes,
                                pos_no=pos_no,
                                pending_yes=pending_yes,
                                pending_no=pending_no,
                                market_state=market_state,
                                client_order_id=getattr(want, "client_order_id", None),
                                order_id=existing.get("id"),
                                api_action=existing.get("api_action"),
                                api_side=existing.get("api_side"),
                            )
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
                        self._emit_order_event(
                            event="AMEND",
                            tick_time=current_time,
                            ticker=ticker,
                            action=want.action,
                            price=want.price,
                            qty=want.qty,
                            is_close=is_close_existing,
                            reason="repriced",
                            cash=cash,
                            pos_yes=pos_yes,
                            pos_no=pos_no,
                            pending_yes=pending_yes,
                            pending_no=pending_no,
                            market_state=market_state,
                            client_order_id=getattr(want, "client_order_id", None),
                            order_id=existing.get("id"),
                            api_action=existing.get("api_action"),
                            api_side=existing.get("api_side"),
                        )
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
                unsatisfied.append(want)

        # Keep close-only orders live until flat, even if strategy returns empty.
        # Use effective inventory (including pending) so closes aren't misclassified.
        net_inv = (pos_yes + pending_yes) - (pos_no + pending_no)
        close_action = None
        if net_inv > 0:
            close_action = "BUY_NO"   # close YES via SELL YES
        elif net_inv < 0:
            close_action = "BUY_YES"  # close NO via SELL NO

        if self.cancel_stale_unmatched:
            for existing in active_orders:
                if existing["id"] in kept_ids:
                    continue
                # REMOVED: Aggressive close protection (lines 764-766) which caused zombie orders.
                # if close_action and existing.get("action") == close_action:
                #    continue
                created_at = self._parse_time(existing.get("created_time"))
                if (
                    self.min_quote_lifetime_s > 0
                    and created_at is not None
                    and (current_time - created_at).total_seconds() < self.min_quote_lifetime_s
                ):
                    continue
                if not self._can_take_action(ticker, current_time.timestamp()):
                    continue
                self._emit_order_event(
                    event="CANCEL",
                    tick_time=current_time,
                    ticker=ticker,
                    action=existing.get("action"),
                    price=existing.get("price"),
                    qty=existing.get("qty"),
                    is_close=existing.get("api_action") == "sell",
                    reason="stale_or_unmatched",
                    cash=cash,
                    pos_yes=pos_yes,
                    pos_no=pos_no,
                    pending_yes=pending_yes,
                    pending_no=pending_no,
                    market_state=market_state,
                    client_order_id=existing.get("client_order_id"),
                    order_id=existing.get("id"),
                    api_action=existing.get("api_action"),
                    api_side=existing.get("api_side"),
                )
                self.adapter.cancel_order(existing["id"])
                self._record_action(ticker, current_time.timestamp())

        for order in unsatisfied:
            order_ticker = order.ticker or ticker
            order_market_state = market_state if order_ticker == ticker else None
            if order_market_state is None:
                get_ms = getattr(self.adapter, "get_latest_market_state", None)
                if callable(get_ms):
                    try:
                        order_market_state = get_ms(order_ticker)
                    except Exception:
                        order_market_state = None

            is_close = self._is_close_action(
                order.action,
                pos_yes,
                pos_no,
                pending_yes,
                pending_no,
            )
            order.is_close = is_close
            now_ts = current_time.timestamp()
            if not order.client_order_id:
                order.client_order_id = self._next_client_order_id(
                    ticker=order.ticker,
                    action=order.action,
                    source=getattr(order, "source", None),
                    now=current_time,
                )
            if order_market_state is None:
                self._emit_order_event(
                    event="SKIP",
                    tick_time=current_time,
                    ticker=order_ticker,
                    action=order.action,
                    price=order.price,
                    qty=order.qty,
                    is_close=is_close,
                    reason="missing_order_ticker_market_state",
                    cash=cash,
                    pos_yes=pos_yes,
                    pos_no=pos_no,
                    pending_yes=pending_yes,
                    pending_no=pending_no,
                    market_state=market_state,
                    client_order_id=order.client_order_id,
                )
                continue
            if not is_close and self._recent_open_reject(order_ticker, now_ts):
                if self.diag_log:
                    self.diag_log(
                        "ORDER_SKIP",
                        tick_ts=current_time,
                        ticker=order_ticker,
                        action=order.action,
                        price=order.price,
                        qty=order.qty,
                        reason="open_reject_cooldown",
                        cash=cash,
                    )
                self._emit_order_event(
                    event="SKIP",
                    tick_time=current_time,
                    ticker=order_ticker,
                    action=order.action,
                    price=order.price,
                    qty=order.qty,
                    is_close=is_close,
                    reason="open_reject_cooldown",
                    cash=cash,
                    pos_yes=pos_yes,
                    pos_no=pos_no,
                    pending_yes=pending_yes,
                    pending_no=pending_no,
                    market_state=order_market_state,
                    client_order_id=order.client_order_id,
                )
                continue
            if (
                not is_close
                and self.enforce_cash_preflight
                and not self._can_afford_open(
                    order,
                    cash,
                    buffer_dollars=self.cash_preflight_buffer_dollars,
                )
            ):
                if self.diag_log:
                    self.diag_log(
                        "ORDER_SKIP",
                        tick_ts=current_time,
                        ticker=order_ticker,
                        action=order.action,
                        price=order.price,
                        qty=order.qty,
                        reason="insufficient_cash_preflight",
                        cash=cash,
                    )
                self._emit_order_event(
                    event="SKIP",
                    tick_time=current_time,
                    ticker=order_ticker,
                    action=order.action,
                    price=order.price,
                    qty=order.qty,
                    is_close=is_close,
                    reason="insufficient_cash_preflight",
                    cash=cash,
                    pos_yes=pos_yes,
                    pos_no=pos_no,
                    pending_yes=pending_yes,
                    pending_no=pending_no,
                    market_state=order_market_state,
                    client_order_id=order.client_order_id,
                )
                continue
            if not self._can_take_action(order_ticker, now_ts):
                self._emit_order_event(
                    event="SKIP",
                    tick_time=current_time,
                    ticker=order_ticker,
                    action=order.action,
                    price=order.price,
                    qty=order.qty,
                    is_close=is_close,
                    reason="action_budget",
                    cash=cash,
                    pos_yes=pos_yes,
                    pos_no=pos_no,
                    pending_yes=pending_yes,
                    pending_no=pending_no,
                    market_state=order_market_state,
                    client_order_id=order.client_order_id,
                )
                continue
            self._emit_order_event(
                event="PLACE",
                tick_time=current_time,
                ticker=order_ticker,
                action=order.action,
                price=order.price,
                qty=order.qty,
                is_close=is_close,
                reason=None,
                cash=cash,
                pos_yes=pos_yes,
                pos_no=pos_no,
                pending_yes=pending_yes,
                pending_no=pending_no,
                market_state=order_market_state,
                client_order_id=order.client_order_id,
            )
            self._emit_trade(
                tick_time=current_time,
                tick_seq=tick_seq,
                tick_source=tick_source,
                tick_row=tick_row,
                ticker=order_ticker,
                action=order.action,
                price=order.price,
                qty=order.qty,
                cash=cash,
                pos_yes=pos_yes,
                pos_no=pos_no,
                pending_yes=pending_yes,
                pending_no=pending_no,
                market_state=order_market_state,
                order_source=getattr(order, "source", None),
            )
            result = self.adapter.place_order(order, order_market_state, current_time)
            self._record_action(order_ticker, now_ts)
            if not is_close and (not result or not getattr(result, "ok", False)):
                self._last_open_reject[order_ticker] = now_ts

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
