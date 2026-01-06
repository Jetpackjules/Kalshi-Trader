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
    ):
        self.strategy = strategy
        self.adapter = adapter
        self.min_requote_interval = float(min_requote_interval)
        self.last_requote_time: dict[str, float] = {}
        self.diag_log = diag_log
        self.diag_every = max(int(diag_every), 1)

    def on_tick(self, *, ticker: str, market_state: dict, current_time: datetime) -> None:
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
                return

        desired_orders = self.strategy.on_market_update(
            ticker,
            market_state,
            current_time,
            portfolios_inventories,
            active_orders,
            self.adapter.get_cash(),
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

        if desired_orders is None:
            return

        self.last_requote_time[ticker] = current_time.timestamp()

        desired = [Order(**o) if isinstance(o, dict) else o for o in desired_orders]

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
            )
