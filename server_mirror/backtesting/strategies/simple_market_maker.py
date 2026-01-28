
from dataclasses import dataclass
from datetime import datetime
import math

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


class SimpleMarketMakerV2:
    def __init__(self, spread_cents: int = 4, risk_pct: float = 0.5, min_qty: int = 1, qty: int = None, max_price: int = 99, skew_factor: float = 0.1, min_gap_cents: int | None = None):
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

    def _fee_cents(self, price_cents: float) -> float:
        # Approx Kalshi convex fee in cents per contract.
        p = float(price_cents) / 100.0
        return 7.0 * p * (1.0 - p)

    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, cash):
        # 1. Get Market Data
        yes_bid = float(market_state.get("yes_bid") or 0)
        yes_ask = float(market_state.get("yes_ask") or 100)
        no_bid = float(market_state.get("no_bid") or 0)
        no_ask = float(market_state.get("no_ask") or 100)
        market_spread = max(0.0, yes_ask - yes_bid)
        
        # 2. Calculate Mid Price
        mid_price = (yes_bid + yes_ask) / 2.0
        # Dynamic gap gate: only open new positions when spread is wide enough to cover fees.
        fee_cents = self._fee_cents(mid_price)
        min_gap = self.min_gap_cents if self.min_gap_cents is not None else max(self.spread_cents, (2 * fee_cents) + 1)
        allow_open = market_spread >= min_gap
        
        # 3. Get Inventory
        # portfolios_inventories is {ticker: {'yes': 10, 'no': 0, ...}}
        # We need net inventory (YES - NO)
        # Wait, engine passes `portfolios_inventories` as dict?
        # Let's assume standard format.
        pos = portfolios_inventories.get(ticker, {})
        yes_inv = int(pos.get("yes", 0))
        no_inv = int(pos.get("no", 0))
        net_inv = yes_inv - no_inv # Positive = Long YES, Negative = Long NO (Short YES)

        reduce_only_threshold = 3

        # 4.5. Arb trigger: cheap asks or crossed bids (inventory-only exits)
        arb_fee_buffer = max(1, int(math.ceil(self._fee_cents(mid_price) * 2)))
        arb_orders = []
        cheap_asks = yes_ask > 0 and no_ask > 0 and (yes_ask + no_ask) <= (100 - arb_fee_buffer)
        crossed_bids = yes_bid > 0 and no_bid > 0 and (yes_bid + no_bid) >= (100 + arb_fee_buffer)

        # If bids are crossed, try to exit inventory at favorable prices.
        if crossed_bids:
            if net_inv > 0:
                close_price = int(max(1, min(99, 100 - yes_bid)))
                close_qty = max(1, min(net_inv, self.fixed_qty or net_inv))
                arb_orders.append(Order(action="BUY_NO", ticker=ticker, qty=close_qty, price=close_price, expiry=None, source="MM_ARB"))
            elif net_inv < 0:
                close_price = int(max(1, min(99, 100 - no_bid)))
                close_qty = max(1, min(abs(net_inv), self.fixed_qty or abs(net_inv)))
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
        half_spread = self.spread_cents / 2.0
        my_bid = int(mid_price - half_spread + skew)
        my_ask = int(mid_price + half_spread + skew)
        
        # 6. Safety Checks
        if my_bid < 1: my_bid = 1
        if my_bid > 99: my_bid = 99
        if my_ask < 1: my_ask = 1
        if my_ask > 99: my_ask = 99
        if my_bid >= my_ask:
            # If skew pushes them together, maintain spread
            # UNLESS we are dumping inventory (skew is large)
            if abs(skew) > self.spread_cents:
                 # Allow tight spread (1 cent) to facilitate dumping
                 my_ask = my_bid + 1
            else:
                 my_ask = my_bid + self.spread_cents
            
            if my_ask > 99:
                my_ask = 99
                my_bid = my_ask - self.spread_cents
                if my_bid < 1: my_bid = 1

        # 6b. Cap skewed quotes so we don't drift too far from the market on thin spreads.
        # Keep quotes within (mid +/- half_spread + 1c buffer).
        half_spread = self.spread_cents / 2.0
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
        # DEBUG PRINTS
        print(f"DEBUG: MM Logic | Ticker={ticker} | Mid={mid_price:.2f} | NetInv={net_inv} | Skew={skew:.2f} | MyBid={my_bid} | MyAsk={my_ask}")

        if self.fixed_qty:
            # Treat fixed_qty as a cap, not a constant size.
            # Scale quantity by the live market spread so we take smaller size on thin gaps.
            market_spread = max(0.0, yes_ask - yes_bid)
            spread_scale = min(1.0, market_spread / max(self.spread_cents, 1))
            base_qty = int(round(self.fixed_qty * spread_scale))
            base_qty = max(self.min_qty, base_qty) if spread_scale > 0 else 0

            bid_qty = base_qty
            ask_qty = base_qty

            # If we have inventory, only size up to what we can close.
            if net_inv > 0:
                # Long YES -> BUY_NO (or SELL YES via adapter) to close.
                # Always allow at least 1 share to exit, regardless of spread scale.
                ask_qty = max(1, min(ask_qty if ask_qty > 0 else 1, net_inv))
            elif net_inv < 0:
                # Long NO -> BUY_YES to close.
                bid_qty = max(1, min(bid_qty if bid_qty > 0 else 1, abs(net_inv)))

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
                    bid_qty = max(1, min(abs(net_inv), bid_qty if bid_qty > 0 else abs(net_inv)))
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
                    ask_qty = net_inv # Dump all
                    ask_qty = min(ask_qty, 200) # Cap
                else:
                    raw_ask_qty = int((cash * self.risk_pct * 100) / no_price)
                    ask_qty = max(self.min_qty, raw_ask_qty)
                    max_affordable_ask = int((cash * 100) / no_price)
                    if ask_qty > max_affordable_ask:
                        ask_qty = max_affordable_ask
            else:
                ask_qty = 0
        
        # 8. Apply Max Price Filter
        if my_bid > self.max_price:
            bid_qty = 0
        if no_price > self.max_price:
            ask_qty = 0
            
        # 9. Reduce Only Logic (Prevent Accumulation of Losing Positions)
        # If we have Net Long YES, do not buy more YES.
        if net_inv >= reduce_only_threshold:
            bid_qty = 0
        # If we have Net Short YES (Long NO), do not buy more NO.
        elif net_inv <= -reduce_only_threshold:
            ask_qty = 0

        # 10. Gap gate: block *opening* orders when spread is too tight.
        # Always allow closing inventory even if the spread is small.
        if not allow_open:
            if net_inv >= 0:
                bid_qty = 0
            if net_inv <= 0:
                ask_qty = 0
            
        print(f"DEBUG: Qty Logic | NetInv={net_inv} | BidQty={bid_qty} | AskQty={ask_qty}")
        
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

def simple_mm_v2_fixed(**kwargs):
    spread = kwargs.get("spread_cents", 4)
    qty = kwargs.get("qty", 100)
    max_p = kwargs.get("max_price", 99)
    skew = kwargs.get("skew_factor", 0.1)
    return SimpleMarketMakerV2(spread_cents=spread, qty=qty, max_price=max_p, skew_factor=skew)
