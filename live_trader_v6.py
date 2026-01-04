import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from collections import defaultdict


def _ensure_import_path() -> None:
    """Allow running from repo root (imports from server_mirror) or on VM home dir."""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if os.path.exists(os.path.join(script_dir, "live_trader_v4.py")):
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        return

    mirror_path = os.path.join(script_dir, "server_mirror")
    if os.path.exists(os.path.join(mirror_path, "live_trader_v4.py")):
        if mirror_path not in sys.path:
            sys.path.insert(0, mirror_path)
        return


_ensure_import_path()

# NOTE: On the VM, live_trader_v4.py sits next to this file.
# Locally, it may live under server_mirror/; _ensure_import_path() handles that.
from live_trader_v4 import (  # type: ignore  # noqa: E402
    LiveTraderV4,
    ComplexStrategy,
    calculate_convex_fee,
    best_yes_ask,
    best_yes_bid,
)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


class InventoryAwareMarketMakerV6(ComplexStrategy):
    """Backtester-parity MM sizing + gating.

    This matches the logic/params in complex_strategy_backtest.py (as closely as practical)
    but returns a (orders, debug) tuple for the V4 engine.
    """

    def __init__(
        self,
        name: str,
        risk_pct: float = 0.5,
        max_inventory: int | None = 50,
        inventory_penalty: float = 0.5,
        max_offset: int = 2,
        alpha: float = 0.1,
        margin_cents: float = 4.0,
        scaling_factor: float = 4.0,
        max_notional_pct: float = 0.05,
        max_loss_pct: float = 0.02,
    ):
        super().__init__(name, risk_pct)
        self.max_inventory = max_inventory
        self.inventory_penalty = inventory_penalty
        self.max_offset = max_offset
        self.alpha = alpha

        self.margin_cents = margin_cents
        self.scaling_factor = scaling_factor
        self.max_notional_pct = max_notional_pct
        self.max_loss_pct = max_loss_pct

        self.fair_prices = {}
        self.last_quote_time = {}
        self.last_mid_snapshot = {}

    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        yes_ask = best_yes_ask(market_state)
        no_ask = market_state.get("no_ask", np.nan)
        yes_bid = best_yes_bid(market_state)

        debug = {"fair": 0.0, "edge": 0.0, "status": "Initializing"}

        if pd.isna(yes_ask) or pd.isna(yes_bid):
            debug["status"] = "Missing price data"
            return None, debug

        mid = (yes_bid + yes_ask) / 2.0
        self.last_mid_snapshot[ticker] = mid
        self.last_quote_time[ticker] = current_time

        hist = self.fair_prices.get(ticker, [])
        hist.append(mid)
        if len(hist) > 20:
            hist.pop(0)
        self.fair_prices[ticker] = hist

        if len(hist) < 20:
            debug["status"] = f"Warmup ({len(hist)}/20)"
            return None, debug

        mean_price = float(np.mean(hist))
        fair_prob = mean_price / 100.0
        debug["fair"] = round(mean_price, 2)

        # Backtester parity: edge computed vs mid-derived price, but order placed at ask.
        price_to_pay_yes = int(mid)
        price_to_pay_no = int(100 - mid)

        edge_yes = fair_prob - (price_to_pay_yes / 100.0)
        edge_no = (1.0 - fair_prob) - (price_to_pay_no / 100.0)

        edge = 0.0
        action = None
        price_to_pay = 0

        if edge_yes > 0:
            edge = float(edge_yes)
            action = "BUY_YES"
            price_to_pay = price_to_pay_yes
        elif edge_no > 0:
            edge = float(edge_no)
            action = "BUY_NO"
            price_to_pay = price_to_pay_no

        if action is None:
            debug["status"] = "No Edge"
            return None, debug

        debug["edge"] = round(edge * 100, 2)

        # Fee/spread gate
        dummy_qty = 10
        fee_est = calculate_convex_fee(price_to_pay, dummy_qty) / dummy_qty
        fee_cents = fee_est * 100
        required_edge_cents = fee_cents + self.margin_cents
        if (edge * 100) < required_edge_cents:
            debug["status"] = f"Edge {edge*100:.2f}c < Req {required_edge_cents:.2f}c"
            return None, debug

        edge_cents = edge * 100.0
        p = price_to_pay / 100.0
        fee_per_contract = 0.07 * p * (1 - p)
        fee_cents_cont = fee_per_contract * 100.0

        edge_after_fee = edge_cents - fee_cents_cont - self.margin_cents
        if edge_after_fee <= 0:
            debug["status"] = f"Edge after fee {edge_after_fee:.2f}c <= 0"
            return None, debug

        scale = min(1.0, edge_after_fee / self.scaling_factor)

        max_notional = spendable_cash * self.max_notional_pct
        max_loss = spendable_cash * self.max_loss_pct

        price_unit = price_to_pay / 100.0
        cost_unit = price_unit + fee_per_contract

        qty_by_notional = int(max_notional / cost_unit) if cost_unit > 0 else 0
        qty_by_loss = int(max_loss / cost_unit) if cost_unit > 0 else 0

        base_qty = min(qty_by_notional, qty_by_loss)
        if base_qty <= 0:
            debug["status"] = f"Size 0 (Cash ${spendable_cash:.2f})"
            return None, debug

        current_inv = inventories.get("YES", 0) if action == "BUY_YES" else inventories.get("NO", 0)
        if self.max_inventory is None:
            room = float("inf")
        else:
            room = self.max_inventory - current_inv
            if room <= 0:
                debug["status"] = f"Inventory Full ({current_inv})"
                return None, debug

        inv_penalty = 1.0 / (1.0 + current_inv / 200.0)
        qty = int(base_qty * scale * inv_penalty)
        qty = max(1, qty)
        if self.max_inventory is not None:
            qty = min(qty, int(room))

        fee_real = calculate_convex_fee(price_to_pay, qty)
        fee_cents_real = (fee_real / qty) * 100.0
        edge_after_fee_real = edge_cents - fee_cents_real - self.margin_cents
        if edge_after_fee_real <= 0:
            debug["status"] = f"Real edge after fee {edge_after_fee_real:.2f}c <= 0"
            return None, debug

        # Execution: place at current ask (like the backtester currently does)
        orders = []
        expiry = datetime.now() + timedelta(seconds=15)

        if action == "BUY_YES":
            if inventories.get("NO", 0) > 0:
                debug["status"] = "Opposite Inventory (NO)"
                return None, debug
            if pd.isna(yes_ask):
                debug["status"] = "Missing YES ask"
                return None, debug
            orders.append(
                {
                    "action": "BUY_YES",
                    "ticker": ticker,
                    "qty": qty,
                    "price": float(yes_ask),
                    "expiry": expiry,
                    "source": "MM",
                    "time": current_time,
                }
            )

        elif action == "BUY_NO":
            if inventories.get("YES", 0) > 0:
                debug["status"] = "Opposite Inventory (YES)"
                return None, debug
            if pd.isna(no_ask):
                debug["status"] = "Missing NO ask"
                return None, debug
            orders.append(
                {
                    "action": "BUY_NO",
                    "ticker": ticker,
                    "qty": qty,
                    "price": float(no_ask),
                    "expiry": expiry,
                    "source": "MM",
                    "time": current_time,
                }
            )

        debug["status"] = f"SIGNAL {action} {qty} @ {price_to_pay} (limit@ask)"
        return orders, debug


class RegimeSwitcherV6(ComplexStrategy):
    def __init__(self, name: str, risk_pct: float = 0.5, tightness_percentile: int = 20, **mm_kwargs):
        super().__init__(name, risk_pct)
        self.mm = InventoryAwareMarketMakerV6("Sub-MM", risk_pct, **mm_kwargs)
        self.spread_histories = defaultdict(list)
        self.tightness_percentile = tightness_percentile
        self.last_decision = {}

    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        yes_ask = best_yes_ask(market_state)
        yes_bid = best_yes_bid(market_state)

        decision = {
            "ticker": ticker,
            "mid": 0.0,
            "spread": 0.0,
            "reason": "Waiting for data...",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }

        if pd.isna(yes_ask) or pd.isna(yes_bid):
            decision["reason"] = "Missing price data"
            self.last_decision = decision
            return None

        spread = yes_ask - yes_bid
        mid = (yes_ask + yes_bid) / 2.0
        decision["mid"] = round(float(mid), 1)
        decision["spread"] = round(float(spread), 1)

        hist = self.spread_histories[ticker]
        hist.append(float(spread))
        if len(hist) > 500:
            hist.pop(0)

        tight_threshold = (
            float(np.percentile(hist, self.tightness_percentile)) if len(hist) > 100 else float(sum(hist) / len(hist))
        )
        is_tight = float(spread) <= tight_threshold

        h = current_time.hour
        is_active_hour = (5 <= h <= 8) or (13 <= h <= 17) or (21 <= h <= 23)

        if not is_active_hour:
            decision["reason"] = f"Outside active hours (Hour: {h})"
        elif not is_tight:
            decision["reason"] = f"Spread {spread:.1f}c > Threshold {tight_threshold:.1f}c"
        else:
            decision["reason"] = "Market Active & Tight"

        mm_active = [o for o in active_orders if o.get("source") == "MM"]
        mm_inv = portfolios_inventories.get("MM", {"YES": 0, "NO": 0})

        mm_orders = None
        mm_debug = None

        if is_active_hour and is_tight:
            mm_orders, mm_debug = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, spendable_cash, idx)
            if mm_debug:
                decision["reason"] = mm_debug.get("status", decision["reason"])
                decision["fair"] = mm_debug.get("fair")
                decision["edge"] = mm_debug.get("edge")
        elif not is_active_hour:
            mm_orders = None
        else:
            mm_orders = []

        self.last_decision = decision

        if mm_orders is None:
            return None

        combined = []
        if mm_orders is not None:
            combined.extend(mm_orders)
        else:
            combined.extend(mm_active)
        return combined


class LiveTraderV6(LiveTraderV4):
    def __init__(
        self,
        *,
        paper: bool = False,
        risk_pct: float = 0.5,
        tightness_percentile: int = 20,
        max_inventory: int | None = None,
        inventory_per_dollar: float | None = None,
        uncap_inventory: bool = False,
    ):
        super().__init__()
        self.paper = paper
        self._max_inventory_override = max_inventory
        self._inventory_per_dollar = inventory_per_dollar
        self._uncap_inventory = uncap_inventory
        self.strategy = RegimeSwitcherV6(
            "Live RegimeSwitcher V6 (Backtester-Parity)",
            risk_pct=risk_pct,
            tightness_percentile=tightness_percentile,
        )

    def _apply_inventory_cap(self) -> None:
        mm = getattr(self.strategy, "mm", None)
        if mm is None or not hasattr(mm, "max_inventory"):
            return

        if self._uncap_inventory:
            mm.max_inventory = None
            print("[CONFIG] max_inventory=None (uncapped)", flush=True)
            return

        if self._max_inventory_override is not None:
            mm.max_inventory = self._max_inventory_override
            print(f"[CONFIG] max_inventory={mm.max_inventory}", flush=True)
            return

        if self._inventory_per_dollar is not None:
            # Use daily_start_equity if available; otherwise fall back to balance.
            base = getattr(self, "daily_start_equity", None)
            if base is None:
                base = getattr(self, "balance", 0.0)

            try:
                cap = int(round(float(base) * float(self._inventory_per_dollar)))
            except Exception:
                cap = 0

            cap = max(1, cap)
            mm.max_inventory = cap
            print(f"[CONFIG] max_inventory={mm.max_inventory} (inventory_per_dollar={self._inventory_per_dollar})", flush=True)

    def place_real_order(self, ticker, qty, price, side, expiry_ts):
        if self.paper:
            print(f"[PAPER] WOULD PLACE: {ticker} {side.upper()} {qty} @ {price} exp={expiry_ts}", flush=True)
            return True
        return super().place_real_order(ticker, qty, price, side, expiry_ts)

    def export_snapshot_now(self, out_path: str | None = None) -> str:
        self.sync_api_state(force_reset_daily=False)
        self._apply_inventory_cap()
        try:
            self.refresh_open_orders_snapshot()
        except Exception:
            pass

        now = datetime.now()
        ts_str = now.strftime("%Y-%m-%d %H:%M:%S")

        if out_path is None:
            snap_dir = os.path.expanduser("~/snapshots")
            os.makedirs(snap_dir, exist_ok=True)
            out_path = os.path.join(snap_dir, f"snapshot_{now.strftime('%Y-%m-%d_%H%M%S')}.json")

        snapshot_data = {
            "timestamp": ts_str,
            "date": now.strftime("%Y-%m-%d"),
            "daily_start_equity": self.daily_start_equity,
            "balance": self.balance,
            "portfolio_value": self.portfolio_value,
            "positions": self.positions,
            "open_orders_snapshot": getattr(self, "open_orders_snapshot", []),
            "strategy_config": {
                "name": self.strategy.name,
                "risk_pct": getattr(self.strategy, "risk_pct", None),
                "tightness_percentile": getattr(self.strategy, "tightness_percentile", None),
            },
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2)

        print(f"[SNAPSHOT] Wrote {out_path}")
        return out_path

    def run(self):
        try:
            mode = "PAPER" if self.paper else "LIVE"
            print(f"=== Live Trader V6 ({mode}) ===", flush=True)
            self.sync_api_state(force_reset_daily=True)
            self._apply_inventory_cap()
            self.update_status_file("STARTING")

            while True:
                if not self.check_control_flag():
                    self.update_status_file("PAUSED")
                    time.sleep(10)
                    continue

                self.update_status_file("RUNNING")
                now = datetime.now()

                if self.last_reset_date != now.strftime("%Y-%m-%d") and now.hour >= 5:
                    self.sync_api_state(force_reset_daily=True)
                    self._apply_inventory_cap()

                all_new_ticks = []
                active_files = self.get_active_log_files()
                for log_file in active_files:
                    ticks = self.fetch_new_ticks(log_file)
                    all_new_ticks.extend(ticks)

                def parse_ts(row):
                    try:
                        return pd.to_datetime(row["timestamp"])
                    except Exception:
                        return datetime.min

                if all_new_ticks:
                    all_new_ticks.sort(key=parse_ts)
                    for row in all_new_ticks:
                        self.on_tick(row)

                if self.last_status_time is None or (now - self.last_status_time).total_seconds() >= 60:
                    self.sync_api_state()
                    self.refresh_open_orders_snapshot()
                    self.print_status()
                    self.last_status_time = now

                time.sleep(1)
        except Exception as e:
            import traceback

            print(f"CRASH: {e}", flush=True)
            print(traceback.format_exc(), flush=True)
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write("\n\n=== CAUGHT EXCEPTION IN RUN() ===\n")
                f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                f.write(traceback.format_exc())
            raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", action="store_true", help="Run active without placing real orders")
    parser.add_argument("--snapshot", action="store_true", help="Write a snapshot now and exit")
    parser.add_argument("--snapshot-out", default=None, help="Optional explicit snapshot output path")
    parser.add_argument("--risk-pct", type=float, default=0.5)
    parser.add_argument("--tightness-percentile", type=int, default=20)
    parser.add_argument("--max-inventory", type=int, default=None, help="Override max inventory cap (contracts)")
    parser.add_argument(
        "--inventory-per-dollar",
        type=float,
        default=0.5,
        help="Set max inventory as round(daily_start_equity * K). Example: if $100 used 50, K=0.5.",
    )
    parser.add_argument("--uncap-inventory", action="store_true", help="Set max_inventory=None (no inventory cap)")

    args = parser.parse_args()

    trader = LiveTraderV6(
        paper=args.paper,
        risk_pct=args.risk_pct,
        tightness_percentile=args.tightness_percentile,
        max_inventory=(int(args.max_inventory) if args.max_inventory is not None else None),
        inventory_per_dollar=(None if args.uncap_inventory or args.max_inventory is not None else args.inventory_per_dollar),
        uncap_inventory=args.uncap_inventory,
    )

    if args.snapshot:
        trader.export_snapshot_now(args.snapshot_out)
        return

    trader.run()


if __name__ == "__main__":
    main()
