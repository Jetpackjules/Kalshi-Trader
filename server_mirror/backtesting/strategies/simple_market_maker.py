
from dataclasses import dataclass
from datetime import datetime
import csv
import json
import math
import os
import time

@dataclass
class Order:
    action: str
    ticker: str
    qty: int
    price: float
    expiry: datetime | None
    source: str = "MM"

class SimpleMarketMaker:
    def __init__(self, spread_cents: int = 4, risk_pct: float = 0.5, min_qty: int = 1, max_qty: int = 100, qty: int = None, max_price: int = 99, max_pos: int = 0, skew_factor: float = 0.0, min_gap_cents: int | None = None):
        if qty:
            self.name = f"SimpleMM_s{spread_cents}_q{qty}_max{max_price}_lim{max_pos}_skew{skew_factor}"
        else:
            self.name = f"SimpleMM_s{spread_cents}_r{int(risk_pct*100)}_min{min_qty}_max{max_qty}_p{max_price}_lim{max_pos}_skew{skew_factor}"
        
        self.spread_cents = spread_cents
        self.risk_pct = risk_pct
        self.min_qty = min_qty
        self.max_qty = max_qty
        self.fixed_qty = qty
        self.max_price = max_price
        self.max_pos = max_pos
        self.skew_factor = skew_factor
        self.min_gap_cents = min_gap_cents

    def _fee_cents(self, price_cents: float) -> float:
        p = float(price_cents) / 100.0
        return 7.0 * p * (1.0 - p)

    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, cash):
        # 1. Get Market Data
        yes_bid = float(market_state.get("yes_bid") or 0)
        yes_ask = float(market_state.get("yes_ask") or 100)
        
        # 2. Calculate Mid Price + dynamic gap gate (fee-aware)
        market_spread = max(0.0, yes_ask - yes_bid)
        mid_price = (yes_bid + yes_ask) / 2.0
        fee_cents = self._fee_cents(mid_price)
        min_gap = self.min_gap_cents if self.min_gap_cents is not None else max(self.spread_cents, (2 * fee_cents) + 1)
        allow_open = market_spread >= min_gap
        
        # 3. Calculate Skew from Inventory
        pos = portfolios_inventories.get(ticker, {})
        yes_inv = int(pos.get("yes", 0))
        no_inv = int(pos.get("no", 0))
        net_inv = yes_inv - no_inv # Positive = Long YES
        
        # Skew: If Long YES (net_inv > 0), we want to lower prices (sell).
        # So we subtract from mid.
        skew = -(net_inv * self.skew_factor)
        
        # 4. Determine Our Quotes
        half_spread = self.spread_cents / 2.0
        my_bid = int(mid_price - half_spread + skew)
        my_ask = int(mid_price + half_spread + skew)
        
        # 4. Safety Checks
        if my_bid < 1: my_bid = 1
        if my_ask > 99: my_ask = 99
        if my_bid >= my_ask:
            my_ask = my_bid + 1
            
        no_price = 100 - my_ask
        
        # 5. Check Inventory Limits (The "Poverty Simulation")
        # If max_pos is set, check current position
        pos = portfolios_inventories.get(ticker, {})
        yes_inv = int(pos.get("yes", 0))
        no_inv = int(pos.get("no", 0))
        
        allow_buy_yes = True
        allow_buy_no = True
        
        if self.max_pos > 0:
            if yes_inv >= self.max_pos:
                allow_buy_yes = False
            if no_inv >= self.max_pos:
                allow_buy_no = False
            
        # 6. Calculate Quantity
        if self.fixed_qty:
            bid_qty = self.fixed_qty
            ask_qty = self.fixed_qty
            # Reduce-only: cap size to inventory when closing.
            if net_inv > 0:
                ask_qty = max(1, min(ask_qty, net_inv))
            elif net_inv < 0:
                bid_qty = max(1, min(bid_qty, abs(net_inv)))
        else:
            # Hybrid Dynamic Logic
            # Bid Side (Buy YES)
            if my_bid > 0:
                # my_bid is in cents; convert to dollars for sizing.
                raw_bid_qty = int((cash * self.risk_pct * 100) / my_bid)
                bid_qty = max(self.min_qty, raw_bid_qty)
                bid_qty = min(self.max_qty, bid_qty) # Cap at max_qty
                if net_inv >= 0:
                    max_affordable_bid = int((cash * 100) / my_bid)
                    if bid_qty > max_affordable_bid:
                        bid_qty = max_affordable_bid
            else:
                bid_qty = 0
            
            # Ask Side (Buy NO)
            if no_price > 0:
                raw_ask_qty = int((cash * self.risk_pct * 100) / no_price)
                ask_qty = max(self.min_qty, raw_ask_qty)
                ask_qty = min(self.max_qty, ask_qty) # Cap at max_qty
                
                if net_inv <= 0:
                    max_affordable_ask = int((cash * 100) / no_price)
                    if ask_qty > max_affordable_ask:
                        ask_qty = max_affordable_ask
            else:
                ask_qty = 0
        
        # 7. Apply Max Price Filter
        if my_bid > self.max_price:
            bid_qty = 0
        if no_price > self.max_price:
            ask_qty = 0
            
        # 8. Apply Inventory Limits
        if not allow_buy_yes:
            bid_qty = 0
        if not allow_buy_no:
            ask_qty = 0

        # 9. Gap gate: block opening orders when spread is too tight.
        if not allow_open:
            if net_inv >= 0:
                bid_qty = 0
            if net_inv <= 0:
                ask_qty = 0
        
        orders = []
        
        if bid_qty > 0:
            orders.append(Order(
                action="BUY_YES",
                ticker=ticker,
                qty=bid_qty,
                price=my_bid,
                expiry=None
            ))
        
        if ask_qty > 0:
            orders.append(Order(
                action="BUY_NO",
                ticker=ticker,
                qty=ask_qty,
                price=no_price,
                expiry=None
            ))
        
        return orders

def simple_mm_hybrid(**kwargs):
    spread = kwargs.get("spread_cents", 4)
    risk = kwargs.get("risk_pct", 0.5)
    min_q = kwargs.get("min_qty", 5)
    max_q = kwargs.get("max_qty", 100)
    max_p = kwargs.get("max_price", 99)
    max_pos = kwargs.get("max_pos", 0)
    skew = kwargs.get("skew_factor", 0.0)
    return SimpleMarketMaker(spread_cents=spread, risk_pct=risk, min_qty=min_q, max_qty=max_q, max_price=max_p, max_pos=max_pos, skew_factor=skew)

def simple_mm_fixed(**kwargs):
    spread = kwargs.get("spread_cents", 4)
    qty = kwargs.get("qty", 10)
    max_p = kwargs.get("max_price", 99)
    max_pos = kwargs.get("max_pos", 0)
    skew = kwargs.get("skew_factor", 0.0)
    return SimpleMarketMaker(spread_cents=spread, qty=qty, max_price=max_p, max_pos=max_pos, skew_factor=skew)


class LadderCache:
    def __init__(self, log_dir: str, refresh_interval_s: float = 2.0):
        self.log_dir = log_dir
        self.refresh_interval_s = refresh_interval_s
        self.cache = {}  # ticker -> {"ts": datetime, "yes": [[p,q]], "no": [[p,q]]}
        self.file_state = {}  # path -> {"offset": int, "last_read": float}

    def _ladder_path(self, ticker: str) -> str:
        try:
            parts = ticker.split('-')
            if len(parts) >= 2:
                market_date_code = f"{parts[0]}-{parts[1]}"
            else:
                market_date_code = "UNKNOWN"
        except Exception:
            market_date_code = "UNKNOWN"
        return os.path.join(self.log_dir, f"orderbook_ladder_{market_date_code}.csv")

    def _refresh_file(self, path: str) -> None:
        try:
            stat = os.stat(path)
        except FileNotFoundError:
            return
        state = self.file_state.get(
            path,
            {"offset": 0, "last_read": 0.0, "inode": None, "mtime": None, "bad_rows": 0},
        )
        inode = getattr(stat, "st_ino", None)
        mtime = stat.st_mtime
        if state["inode"] is None:
            state["inode"] = inode
            state["mtime"] = mtime
        if inode is not None and state["inode"] != inode:
            state["offset"] = 0
            state["inode"] = inode
        if state["mtime"] is not None and state["mtime"] != mtime:
            # File rotated/rewritten.
            state["offset"] = 0
            state["mtime"] = mtime
        if stat.st_size < state["offset"]:
            state["offset"] = 0
        if time.time() - state["last_read"] < self.refresh_interval_s:
            return
        with open(path, "r", encoding="utf-8") as f:
            if state["offset"] > 0:
                f.seek(state["offset"])
                # Discard partial line if we seeked into the middle of a row.
                f.readline()
            reader = csv.reader(f)
            if state["offset"] == 0:
                next(reader, None)
            for row in reader:
                if len(row) < 4:
                    state["bad_rows"] += 1
                    if state["bad_rows"] % 25 == 0:
                        print(f"DEBUG: LadderCache skipped {state['bad_rows']} bad rows in {path}")
                    continue
                ts_raw, ticker, yes_raw, no_raw = row[0], row[1], row[2], row[3]
                if not ticker:
                    state["bad_rows"] += 1
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except Exception:
                    state["bad_rows"] += 1
                    continue
                try:
                    yes = json.loads(yes_raw) if yes_raw else []
                    no = json.loads(no_raw) if no_raw else []
                    yes = [[int(p), int(q)] for p, q in yes]
                    no = [[int(p), int(q)] for p, q in no]
                except Exception:
                    state["bad_rows"] += 1
                    continue
                self.cache[ticker] = {"ts": ts, "yes": yes, "no": no}
            state["offset"] = f.tell()
            state["last_read"] = time.time()
        self.file_state[path] = state

    def get(self, ticker: str, now: datetime):
        path = self._ladder_path(ticker)
        self._refresh_file(path)
        return self.cache.get(ticker)

class SimpleMarketMakerV2:
    def __init__(self, spread_cents: int = 4, risk_pct: float = 0.5, min_qty: int = 1, qty: int = None, max_price: int = 99, skew_factor: float = 0.1, min_gap_cents: int | None = None,
                 ladder_depth: int = 10, ladder_stale_s: float = 10.0, ladder_refresh_s: float = 2.0,
                 ladder_min_depth_qty: int = 10, exit_slip_cents: int = 1, exit_safety_factor: float = 0.5,
                 open_slip_cents: int = 1,
                 open_edge_buffer_cents: int = 3,
                 maker_only_opens: bool = True,
                 enable_taker_arb: bool = False):
        if qty:
            self.name = f"SimpleMMv2_s{spread_cents}_q{qty}_max{max_price}_skew{skew_factor}"
        else:
            self.name = f"SimpleMMv2_s{spread_cents}_r{int(risk_pct*100)}_min{min_qty}_max{max_price}_skew{skew_factor}"

        self.spread_cents = spread_cents
        self.risk_pct = risk_pct
        self.min_qty = min_qty
        self.fixed_qty = qty
        self.max_price = max_price
        self.skew_factor = skew_factor
        self.min_gap_cents = min_gap_cents
        self.ladder_depth = ladder_depth
        self.ladder_stale_s = ladder_stale_s
        self.ladder_refresh_s = ladder_refresh_s
        self.ladder_min_depth_qty = ladder_min_depth_qty
        self.exit_slip_cents = exit_slip_cents
        self.exit_safety_factor = exit_safety_factor
        self.open_slip_cents = open_slip_cents
        # Extra cents required beyond round-trip fee before opening. This is a cheap way to
        # avoid negative-EV "micro-edge" churn (fees are convex around ~50c).
        self.open_edge_buffer_cents = int(open_edge_buffer_cents)
        self.maker_only_opens = bool(maker_only_opens)
        self.enable_taker_arb = bool(enable_taker_arb)
        self._ladder_cache = LadderCache(log_dir=os.environ.get("KALSHI_LOG_DIR", "market_logs"),
                                         refresh_interval_s=ladder_refresh_s)
        self.debug = os.environ.get("MM_DEBUG") == "1"
        # Reduce-only lock & stuck-close probes.
        self.reduce_only_lock_after_s = 30.0
        self.reduce_only_unlock_after_s = 60.0
        self.stuck_probe_after_s = 15.0
        self.stuck_probe_cooldown_s = 60.0
        self._allow_open_false_since = {}
        self._allow_open_good_since = {}
        self._reduce_only_lock = {}
        self._stuck_close_since = {}
        self._stuck_close_last = {}

    def _fee_cents(self, price_cents: float) -> float:
        # Approx Kalshi convex fee in cents per contract.
        p = float(price_cents) / 100.0
        return 7.0 * p * (1.0 - p)

    def _required_slip(self, levels, qty):
        if not levels or qty <= 0:
            return None
        best_price = levels[0][0]
        cumulative = 0
        for price, size in levels:
            cumulative += int(size)
            if cumulative >= qty:
                return int(best_price - price)
        return None

    def _available_within(self, levels, max_slip):
        if not levels:
            return 0
        best_price = levels[0][0]
        threshold = best_price - max_slip
        return sum(int(q) for p, q in levels if p >= threshold)

    def _ladder_for_ticker(self, ticker, current_time):
        ladder = self._ladder_cache.get(ticker, current_time)
        if not ladder:
            return None
        age_s = (current_time - ladder["ts"]).total_seconds()
        if age_s > self.ladder_stale_s:
            return None
        ladder["yes"] = sorted(ladder["yes"], key=lambda x: x[0], reverse=True)
        ladder["no"] = sorted(ladder["no"], key=lambda x: x[0], reverse=True)
        return ladder

    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, cash):
        # 1. Get Market Data
        yes_bid = float(market_state.get("yes_bid") or 0)
        yes_ask = float(market_state.get("yes_ask") or 100)
        no_bid = float(market_state.get("no_bid") or 0)
        no_ask = float(market_state.get("no_ask") or 100)
        market_spread = max(0.0, yes_ask - yes_bid)

        ladder = self._ladder_for_ticker(ticker, current_time)
        yes_bids = ladder["yes"] if ladder else []
        no_bids = ladder["no"] if ladder else []
        exit_yes_liq = self._available_within(yes_bids, self.exit_slip_cents) if yes_bids else 0
        exit_no_liq = self._available_within(no_bids, self.exit_slip_cents) if no_bids else 0
        
        # 2. Calculate Mid Price
        mid_price = (yes_bid + yes_ask) / 2.0
        # Microprice (book-weighted mid) using bid sizes + implied ask sizes from the opposite-side bid.
        # This improves adverse-selection handling without requiring any extra API calls.
        micro_mid = mid_price
        imbalance_spread = 0
        if yes_bids and no_bids:
            best_yes_bid_p, best_yes_bid_q = int(yes_bids[0][0]), int(yes_bids[0][1])
            best_no_bid_p, best_no_bid_q = int(no_bids[0][0]), int(no_bids[0][1])
            implied_yes_ask_p = 100 - best_no_bid_p
            implied_yes_ask_q = best_no_bid_q
            denom = max(1, best_yes_bid_q + implied_yes_ask_q)
            micro_mid = (best_yes_bid_p * implied_yes_ask_q + implied_yes_ask_p * best_yes_bid_q) / denom
            # Clamp inside [bid, implied_ask] for sanity.
            micro_mid = max(min(micro_mid, float(implied_yes_ask_p)), float(best_yes_bid_p))
            # When the ladder is imbalanced/thin, quote a bit wider (reduces churn/pickoff risk).
            imbalance = abs(best_yes_bid_q - implied_yes_ask_q) / denom
            imbalance_spread = int(round(imbalance * 2.0))  # 0..2ish
        # Dynamic gap gate: only open new positions when spread is wide enough to cover fees.
        fee_cents = self._fee_cents(mid_price)
        min_gap = self.min_gap_cents if self.min_gap_cents is not None else max(
            self.spread_cents,
            (2 * fee_cents) + self.open_edge_buffer_cents,
        )
        allow_open = market_spread >= min_gap

        # When opening, we also use a fee-aware quoting spread (in cents). This ensures our *own*
        # intended capture is not smaller than the round-trip fee curve + buffer.
        open_quote_spread = int(math.ceil(min_gap)) + imbalance_spread
        if open_quote_spread < 2:
            open_quote_spread = 2
        
        # 3. Get Inventory
        # portfolios_inventories is {ticker: {'yes': 10, 'no': 0, ...}}
        # We need net inventory (YES - NO)
        # Wait, engine passes `portfolios_inventories` as dict?
        # Let's assume standard format.
        pos = portfolios_inventories.get(ticker, {})
        yes_inv = int(pos.get("yes", 0))
        no_inv = int(pos.get("no", 0))
        net_inv = yes_inv - no_inv # Positive = Long YES, Negative = Long NO (Short YES)
        if ladder is None and net_inv != 0:
            allow_open = False
        now_ts = current_time.timestamp()
        # Reduce-only lock when spreads stay bad for a while.
        if not allow_open:
            since = self._allow_open_false_since.get(ticker, now_ts)
            self._allow_open_false_since[ticker] = since
            self._allow_open_good_since.pop(ticker, None)
            if now_ts - since >= self.reduce_only_lock_after_s:
                self._reduce_only_lock[ticker] = True
        else:
            self._allow_open_false_since.pop(ticker, None)
            if self._reduce_only_lock.get(ticker):
                good_since = self._allow_open_good_since.get(ticker, now_ts)
                self._allow_open_good_since[ticker] = good_since
                if net_inv == 0 or (ladder is not None and now_ts - good_since >= self.reduce_only_unlock_after_s):
                    self._reduce_only_lock.pop(ticker, None)
                    self._allow_open_good_since.pop(ticker, None)
            else:
                self._allow_open_good_since.pop(ticker, None)
        if self._reduce_only_lock.get(ticker):
            allow_open = False

        reduce_only_threshold = 3

        # 4.5. Arb trigger: cheap asks or crossed bids (inventory-only exits)
        arb_fee_buffer = max(1, int(math.ceil(self._fee_cents(mid_price) * 2)))
        arb_orders = []
        # Buying both asks is taker-heavy; keep it off by default unless explicitly enabled.
        cheap_asks = (
            self.enable_taker_arb
            and yes_ask > 0
            and no_ask > 0
            and (yes_ask + no_ask) <= (100 - arb_fee_buffer)
        )
        crossed_bids = yes_bid > 0 and no_bid > 0 and (yes_bid + no_bid) >= (100 + arb_fee_buffer)

        # If bids are crossed, try to exit inventory at favorable prices.
        if crossed_bids:
            if net_inv > 0:
                close_qty = max(1, min(net_inv, exit_yes_liq if exit_yes_liq else net_inv))
                slip = self._required_slip(yes_bids, close_qty) if yes_bids else 0
                slip = min(slip or 0, self.exit_slip_cents)
                yes_sell = int(max(1, yes_bids[0][0] - slip)) if yes_bids else int(yes_bid)
                close_price = int(max(1, min(99, 100 - yes_sell)))
                arb_orders.append(Order(action="BUY_NO", ticker=ticker, qty=close_qty, price=close_price, expiry=None, source="MM_ARB"))
            elif net_inv < 0:
                close_qty = max(1, min(abs(net_inv), exit_no_liq if exit_no_liq else abs(net_inv)))
                slip = self._required_slip(no_bids, close_qty) if no_bids else 0
                slip = min(slip or 0, self.exit_slip_cents)
                no_sell = int(max(1, no_bids[0][0] - slip)) if no_bids else int(no_bid)
                close_price = int(max(1, min(99, 100 - no_sell)))
                arb_orders.append(Order(action="BUY_YES", ticker=ticker, qty=close_qty, price=close_price, expiry=None, source="MM_ARB"))
            if arb_orders:
                return arb_orders

        # If asks are cheap enough, buy both sides (only if we're near flat).
        if cheap_asks and abs(net_inv) <= reduce_only_threshold:
            yes_px = int(math.ceil(yes_ask))
            no_px = int(math.ceil(no_ask))
            pair_cost = (yes_px + no_px) / 100.0
            max_pairs_cash = int((cash * 100) / max(yes_px + no_px, 1))
            max_pairs_risk = int((cash * self.risk_pct) / max(pair_cost, 0.01))
            arb_qty = max(self.min_qty, max_pairs_risk)
            if self.fixed_qty:
                arb_qty = min(arb_qty, self.fixed_qty)
            arb_qty = min(arb_qty, max_pairs_cash)
            if arb_qty > 0:
                return [
                    Order(action="BUY_YES", ticker=ticker, qty=arb_qty, price=yes_px, expiry=None, source="MM_ARB"),
                    Order(action="BUY_NO", ticker=ticker, qty=arb_qty, price=no_px, expiry=None, source="MM_ARB"),
                ]
        
        # 4. Calculate Skew
        # If we are Long YES (net_inv > 0), we want to sell YES -> Lower prices
        # skew should be negative to lower bid/ask
        skew = -(net_inv * self.skew_factor)
        
        # 5. Determine Our Quotes with Skew
        # Use fee-aware spread for quoting when flat/opening; when carrying inventory, skew is
        # the main driver and we'll override into close-only anyway.
        half_spread = open_quote_spread / 2.0
        anchor_mid = micro_mid
        my_bid = int(anchor_mid - half_spread + skew)
        my_ask = int(anchor_mid + half_spread + skew)
        
        # 6. Safety Checks
        if my_bid < 1: my_bid = 1
        if my_bid > 99: my_bid = 99
        if my_ask < 1: my_ask = 1
        if my_ask > 99: my_ask = 99
        if my_bid >= my_ask:
            # If skew pushes them together, maintain spread
            # UNLESS we are dumping inventory (skew is large)
            if abs(skew) > open_quote_spread:
                 # Allow tight spread (1 cent) to facilitate dumping
                 my_ask = my_bid + 1
            else:
                 my_ask = my_bid + open_quote_spread
            
            if my_ask > 99:
                my_ask = 99
                my_bid = my_ask - open_quote_spread
                if my_bid < 1: my_bid = 1

        # 6b. Cap skewed quotes so we don't drift too far from the market on thin spreads.
        # Keep quotes within (mid +/- half_spread + 1c buffer).
        half_spread = open_quote_spread / 2.0
        max_ask = int(mid_price + half_spread + 1)
        min_bid = int(mid_price - half_spread - 1)
        if max_ask < 1: max_ask = 1
        if min_bid < 1: min_bid = 1

        if my_ask > max_ask:
            my_ask = max_ask
            if my_bid >= my_ask:
                my_bid = max(1, my_ask - 1)

        if my_bid < min_bid:
            my_bid = min_bid
            if my_bid >= my_ask:
                my_ask = min(99, my_bid + 1)

        # 6c. Hard cap ask to current best ask (if known) so we don't quote above market.
        # This prevents selling far above a 0-1c market.
        if yes_ask > 0 and yes_ask < 100:
            my_ask = min(my_ask, int(yes_ask))
            if my_bid >= my_ask:
                my_bid = max(1, my_ask - 1)

        no_price = 100 - my_ask
            
        # 7. Calculate Quantity

        if self.fixed_qty:
            # Treat fixed_qty as a cap, not a constant size.
            # Scale quantity by the live market spread so we take smaller size on thin gaps.
            market_spread = max(0.0, yes_ask - yes_bid)
            spread_scale = min(1.0, market_spread / max(open_quote_spread, 1))
            base_qty = int(round(self.fixed_qty * spread_scale))
            base_qty = max(self.min_qty, base_qty) if spread_scale > 0 else 0

            bid_qty = base_qty
            ask_qty = base_qty

            # If we have inventory, only size up to what we can close.
            if net_inv > 0:
                # Long YES -> BUY_NO (or SELL YES via adapter) to close.
                # Always allow at least 1 share to exit, regardless of spread scale.
                close_cap = exit_yes_liq if yes_bids else net_inv
                ask_qty = min(net_inv, close_cap) if close_cap > 0 else 0
                if ask_qty > 0:
                    ask_qty = max(1, min(ask_qty if ask_qty > 0 else 1, net_inv, close_cap))
            elif net_inv < 0:
                # Long NO -> BUY_YES to close.
                close_cap = exit_no_liq if no_bids else abs(net_inv)
                bid_qty = min(abs(net_inv), close_cap) if close_cap > 0 else 0
                if bid_qty > 0:
                    bid_qty = max(1, min(bid_qty if bid_qty > 0 else 1, abs(net_inv), close_cap))

            # Depth gate for opening (near flat only). If ladder is present, treat 0 depth as 0.
            if net_inv >= 0 and ladder is not None and exit_yes_liq < self.ladder_min_depth_qty:
                bid_qty = 0
            if net_inv <= 0 and ladder is not None and exit_no_liq < self.ladder_min_depth_qty:
                ask_qty = 0

            # Size cap based on exit liquidity
            if net_inv <= 0 and ladder is not None:
                max_open_yes = max(0, int(exit_yes_liq * self.exit_safety_factor))
                bid_qty = min(bid_qty, max_open_yes) if max_open_yes > 0 else 0
            if net_inv >= 0 and ladder is not None:
                max_open_no = max(0, int(exit_no_liq * self.exit_safety_factor))
                ask_qty = min(ask_qty, max_open_no) if max_open_no > 0 else 0

            # Open slip gate: only open if the ladder can absorb our size within open_slip_cents.
            if bid_qty > 0 and net_inv >= 0 and yes_bids:
                required_slip = self._required_slip(yes_bids, bid_qty)
                if required_slip is None or required_slip > self.open_slip_cents:
                    bid_qty = min(bid_qty, self._available_within(yes_bids, self.open_slip_cents))
            if ask_qty > 0 and net_inv <= 0 and no_bids:
                required_slip = self._required_slip(no_bids, ask_qty)
                if required_slip is None or required_slip > self.open_slip_cents:
                    ask_qty = min(ask_qty, self._available_within(no_bids, self.open_slip_cents))

            # Cash caps: skip for close-only YES side, since selling NO doesn't require extra cash.
            if my_bid > 0:
                if net_inv >= 0:
                    max_affordable_bid = int((cash * 100) / my_bid)
                    if bid_qty > max_affordable_bid:
                        bid_qty = max_affordable_bid
            else:
                bid_qty = 0

            if net_inv <= 0:
                if no_price > 0:
                    max_affordable_ask = int((cash * 100) / no_price)
                    if ask_qty > max_affordable_ask:
                        ask_qty = max_affordable_ask
                else:
                    ask_qty = 0

        else:
            # Hybrid Dynamic Logic
            if my_bid > 0:
                raw_bid_qty = int((cash * self.risk_pct * 100) / my_bid)
                bid_qty = max(self.min_qty, raw_bid_qty)
                # If we're closing a NO position, allow at least 1 share regardless of cash.
                if net_inv < 0:
                    close_cap = exit_no_liq if exit_no_liq else abs(net_inv)
                    bid_qty = max(1, min(abs(net_inv), close_cap, bid_qty if bid_qty > 0 else abs(net_inv)))
                else:
                    max_affordable_bid = int((cash * 100) / my_bid)
                    if bid_qty > max_affordable_bid:
                        bid_qty = max_affordable_bid
            else:
                bid_qty = 0
            
            if no_price > 0:
                # If we are Long YES (NetInv > 0), we are Buying NO to close.
                # This does NOT require cash (it generates cash).
                if net_inv > 0:
                    close_cap = exit_yes_liq if yes_bids else net_inv
                    ask_qty = min(net_inv, close_cap) if close_cap > 0 else 0
                    if ask_qty > 0:
                        ask_qty = min(ask_qty, 200) # Cap
                else:
                    raw_ask_qty = int((cash * self.risk_pct * 100) / no_price)
                    ask_qty = max(self.min_qty, raw_ask_qty)
                    max_affordable_ask = int((cash * 100) / no_price)
                    if ask_qty > max_affordable_ask:
                        ask_qty = max_affordable_ask
            else:
                ask_qty = 0

            # Depth gate for opening (near flat only)
            if net_inv >= 0 and exit_yes_liq and exit_yes_liq < self.ladder_min_depth_qty:
                bid_qty = 0
            if net_inv <= 0 and exit_no_liq and exit_no_liq < self.ladder_min_depth_qty:
                ask_qty = 0

            # Size cap based on exit liquidity
            if net_inv <= 0 and exit_yes_liq:
                max_open_yes = max(0, int(exit_yes_liq * self.exit_safety_factor))
                bid_qty = min(bid_qty, max_open_yes) if max_open_yes > 0 else 0
            if net_inv >= 0 and exit_no_liq:
                max_open_no = max(0, int(exit_no_liq * self.exit_safety_factor))
                ask_qty = min(ask_qty, max_open_no) if max_open_no > 0 else 0

            # Open slip gate: only open if the ladder can absorb our size within open_slip_cents.
            if bid_qty > 0 and net_inv >= 0 and yes_bids:
                required_slip = self._required_slip(yes_bids, bid_qty)
                if required_slip is None or required_slip > self.open_slip_cents:
                    bid_qty = min(bid_qty, self._available_within(yes_bids, self.open_slip_cents))
            if ask_qty > 0 and net_inv <= 0 and no_bids:
                required_slip = self._required_slip(no_bids, ask_qty)
                if required_slip is None or required_slip > self.open_slip_cents:
                    ask_qty = min(ask_qty, self._available_within(no_bids, self.open_slip_cents))
        
        # 8. Apply Max Price Filter (opening only)
        if net_inv >= 0 and my_bid > self.max_price:
            bid_qty = 0
        if net_inv <= 0 and no_price > self.max_price:
            ask_qty = 0
            
        # 9. Reduce Only Logic (Prevent Accumulation of Losing Positions)
        # If we have Net Long YES, do not buy more YES.
        if net_inv >= reduce_only_threshold:
            bid_qty = 0
        # If we have Net Short YES (Long NO), do not buy more NO.
        elif net_inv <= -reduce_only_threshold:
            ask_qty = 0

        # 10. Gap gate: block *opening* orders when spread is too tight.
        if not allow_open:
            if net_inv >= 0:
                bid_qty = 0
            if net_inv <= 0:
                ask_qty = 0

        # 11. Closing overrides: never block close attempts with open gates.
        close_bid_qty = 0
        close_ask_qty = 0
        if net_inv > 0:
            close_cap = exit_yes_liq if yes_bids else net_inv
            close_ask_qty = min(net_inv, close_cap) if close_cap > 0 else 0
            ask_qty = close_ask_qty
            bid_qty = 0
            # Close price: sell YES into the ladder bid (expressed as BUY_NO price).
            if yes_bids:
                best_yes_bid = int(yes_bids[0][0])
                yes_sell = max(1, best_yes_bid - int(self.exit_slip_cents))
                no_price = max(1, min(99, 100 - yes_sell))
        elif net_inv < 0:
            close_cap = exit_no_liq if no_bids else abs(net_inv)
            close_bid_qty = min(abs(net_inv), close_cap) if close_cap > 0 else 0
            bid_qty = close_bid_qty
            ask_qty = 0
            # Close price: sell NO into the ladder bid (expressed as BUY_YES price).
            if no_bids:
                best_no_bid = int(no_bids[0][0])
                no_sell = max(1, best_no_bid - int(self.exit_slip_cents))
                my_bid = max(1, min(99, 100 - no_sell))

        # Maker-only opens: avoid crossing the current ask (taker). This is only applied when
        # flat (net_inv == 0); closes are allowed to be aggressive.
        if self.maker_only_opens and net_inv == 0:
            if bid_qty > 0 and yes_ask and yes_ask < 100:
                yes_ask_int = int(math.floor(yes_ask))
                if my_bid >= yes_ask_int:
                    my_bid = max(1, yes_ask_int - 1)
            if ask_qty > 0 and no_ask and no_ask < 100:
                no_ask_int = int(math.floor(no_ask))
                if no_price >= no_ask_int:
                    no_price = max(1, no_ask_int - 1)
                    # Keep the derived YES-ask consistent for any downstream math/logs.
                    my_ask = 100 - no_price
                    if my_bid >= my_ask:
                        my_bid = max(1, my_ask - 1)

        # Quote lifetime economics: if our current intended round-trip edge is not fee-positive,
        # don't keep posting just to "be present." This avoids low-edge churn.
        if net_inv == 0 and (bid_qty > 0 or ask_qty > 0):
            implied_yes_ask = float(100 - no_price)
            gross_edge_c = float(implied_yes_ask) - float(my_bid)
            fee_edge_c = self._fee_cents(my_bid) + self._fee_cents(implied_yes_ask)
            net_edge_c = gross_edge_c - fee_edge_c
            if net_edge_c < 1.0:
                bid_qty = 0
                ask_qty = 0

        if self.debug and (bid_qty > 0 or ask_qty > 0):
            print(
                f"DEBUG: MM | {ticker} mid={mid_price:.2f} spread={market_spread:.2f} "
                f"net={net_inv} bid={my_bid}@{bid_qty} ask={no_price}@{ask_qty} "
                f"allow_open={allow_open} exit_yes_liq={exit_yes_liq} exit_no_liq={exit_no_liq}"
            )
        
        orders = []

        # Per-tick expected edge logging (compact). We compute the intended YES round-trip capture
        # implied by our two quotes: buy YES @ my_bid, sell YES @ my_ask (= 100 - no_price).
        implied_yes_ask = float(100 - no_price)
        gross_edge_c = float(implied_yes_ask) - float(my_bid)
        fee_edge_c = self._fee_cents(my_bid) + self._fee_cents(implied_yes_ask)
        net_edge_c = gross_edge_c - fee_edge_c
        edge_tag = f"ge={gross_edge_c:.1f}c fee={fee_edge_c:.2f}c ne={net_edge_c:.2f}c"
        edge_tag += f" mid={mid_price:.1f} micro={micro_mid:.1f} sp={open_quote_spread}"
        
        if bid_qty > 0:
            is_close = net_inv < 0
            source = ("MM_CLOSE" if is_close else "MM_OPEN") + f"({edge_tag})"
            orders.append(Order(
                action="BUY_YES",
                ticker=ticker,
                qty=bid_qty,
                price=my_bid,
                expiry=None,
                source=source,
            ))
        
        if ask_qty > 0:
            is_close = net_inv > 0
            source = ("MM_CLOSE" if is_close else "MM_OPEN") + f"({edge_tag})"
            orders.append(Order(
                action="BUY_NO",
                ticker=ticker,
                qty=ask_qty,
                price=no_price,
                expiry=None,
                source=source,
            ))

        # Stuck-close probe: if ladder exists but no exit liquidity, poke a 1-lot close.
        if net_inv > 0:
            if ladder is not None and exit_yes_liq == 0 and ask_qty == 0:
                # Micro-guard: don't stack probe closes on top of an already-live close order.
                has_active_close = any(
                    (o.get("api_action") == "sell" and o.get("api_side") == "yes")
                    for o in (active_orders or [])
                )
                if has_active_close:
                    return orders
                since = self._stuck_close_since.get(ticker, now_ts)
                self._stuck_close_since[ticker] = since
                last_probe = self._stuck_close_last.get(ticker, 0.0)
                if now_ts - since >= self.stuck_probe_after_s and now_ts - last_probe >= self.stuck_probe_cooldown_s:
                    best_yes = yes_bids[0][0] if yes_bids else int(yes_bid)
                    if best_yes > 0:
                        yes_sell = max(1, int(best_yes) - self.exit_slip_cents)
                        probe_price = max(1, min(99, 100 - yes_sell))
                        orders.append(
                            Order(
                                action="BUY_NO",
                                ticker=ticker,
                                qty=1,
                                price=probe_price,
                                expiry=None,
                                source="MM_PROBE",
                            )
                        )
                        self._stuck_close_last[ticker] = now_ts
            else:
                self._stuck_close_since.pop(ticker, None)
                self._stuck_close_last.pop(ticker, None)
        elif net_inv < 0:
            if ladder is not None and exit_no_liq == 0 and bid_qty == 0:
                has_active_close = any(
                    (o.get("api_action") == "sell" and o.get("api_side") == "no")
                    for o in (active_orders or [])
                )
                if has_active_close:
                    return orders
                since = self._stuck_close_since.get(ticker, now_ts)
                self._stuck_close_since[ticker] = since
                last_probe = self._stuck_close_last.get(ticker, 0.0)
                if now_ts - since >= self.stuck_probe_after_s and now_ts - last_probe >= self.stuck_probe_cooldown_s:
                    best_no = no_bids[0][0] if no_bids else int(no_bid)
                    if best_no > 0:
                        no_sell = max(1, int(best_no) - self.exit_slip_cents)
                        probe_price = max(1, min(99, 100 - no_sell))
                        orders.append(
                            Order(
                                action="BUY_YES",
                                ticker=ticker,
                                qty=1,
                                price=probe_price,
                                expiry=None,
                                source="MM_PROBE",
                            )
                        )
                        self._stuck_close_last[ticker] = now_ts
            else:
                self._stuck_close_since.pop(ticker, None)
                self._stuck_close_last.pop(ticker, None)
        else:
            self._stuck_close_since.pop(ticker, None)
            self._stuck_close_last.pop(ticker, None)
        
        return orders

def simple_mm_v2_fixed(**kwargs):
    spread = kwargs.get("spread_cents", 4)
    qty = kwargs.get("qty", 100)
    max_p = kwargs.get("max_price", 99)
    skew = kwargs.get("skew_factor", 0.1)
    return SimpleMarketMakerV2(spread_cents=spread, qty=qty, max_price=max_p, skew_factor=skew)
