from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta
import logging
import sys
import traceback
from zoneinfo import ZoneInfo

from backtesting.engine import parse_market_date_from_ticker
from backtesting.strategies.nws_regime_split_f6_0322 import NWSRegimeSplitF60322Trader



class NWSRegimeSplitF60322EquityTargetTrader(NWSRegimeSplitF60322Trader):
    """
    Champion logic, but position sizing targets a fraction of total equity
    (cash + marked value of open positions), capped by available cash.
    """

    def __init__(self, **kwargs):
        self.decision_anchor_mode = kwargs.pop("decision_anchor_mode", "rolling_latest")
        self.forecast_delay_minutes = int(kwargs.get("forecast_delay_minutes", 171)) # Default from base if not provided
        super().__init__(**kwargs)
        self._latest_yes_bid: dict[str, float] = {}
        self._latest_yes_bid: dict[str, float] = {}
        self._latest_no_bid: dict[str, float] = {}
        # logging.basicConfig(level=logging.INFO, format='%(message)s', force=True)

    def _log(self, msg: str, throttle: bool = False, throttle_seconds: int = 60):
        now = datetime.now().timestamp()
        if throttle:
            if msg == self._last_log_msg and (now - self._last_log_ts) < throttle_seconds:
                return
        elif msg == self._last_log_msg:
             return

        sys.stdout.write(f"[NWS] {msg}\n")
        sys.stdout.flush()
        self._last_log_msg = msg
        self._last_log_ts = now

        
    def _decision_anchor_for_target(self, target_date: date, now_local: datetime) -> datetime:

        if self.decision_anchor_mode == "rolling_latest":
             return now_local
        
        # Fallback to static "Day-Before 17:00" logic from base class
        # (Replicated here since base doesn't expose it as a reusable method)
        return datetime.combine(target_date - timedelta(days=1), self.entry_time, tzinfo=self.local_tz)

    def _estimate_total_equity(self, cash: float, inventories) -> float:
        total = float(cash)
        if not isinstance(inventories, dict):
            return total

        for tkr, inv in inventories.items():
            if not isinstance(inv, dict):
                continue
            yes_qty = int(inv.get("yes") or inv.get("YES") or 0)
            no_qty = int(inv.get("no") or inv.get("NO") or 0)
            if yes_qty <= 0 and no_qty <= 0:
                continue

            yb = self._latest_yes_bid.get(tkr)
            nb = self._latest_no_bid.get(tkr)
            ya = self._latest_yes_ask.get(tkr)
            na = self._latest_no_ask.get(tkr)

            # Primary mark: bid, then ask.
            yes_px = yb if yb is not None else ya
            no_px = nb if nb is not None else na

            # Fallback mark: if we don't have quotes for a held leg, value at $1 notional.
            # This prevents open positions from being treated as zero during cross-ticker updates.
            if yes_px is None and yes_qty > 0:
                yes_px = 100.0
            if no_px is None and no_qty > 0:
                no_px = 100.0

            total += (yes_qty * float(yes_px or 0.0) + no_qty * float(no_px or 0.0)) / 100.0
        return total

    def on_market_update(
        self,
        ticker,
        market_state,
        current_time,
        portfolios_inventories,
        active_orders,
        cash,
    ):
        self.last_gate_reason = None
        self.last_gate_detail = None

        market_dt = parse_market_date_from_ticker(ticker)
        if market_dt is not None:
            self._ticker_market_date[ticker] = market_dt.date()

        yes_bid = market_state.get("yes_bid")
        no_bid = market_state.get("no_bid")
        yes_ask = market_state.get("yes_ask")
        no_ask = market_state.get("no_ask")
        if yes_bid is not None:
            self._latest_yes_bid[ticker] = float(yes_bid)
        if no_bid is not None:
            self._latest_no_bid[ticker] = float(no_bid)
        try:
            if yes_ask is not None:
                self._latest_yes_ask[ticker] = float(yes_ask)
            if no_ask is not None:
                self._latest_no_ask[ticker] = float(no_ask)

            # Fix: Engine provides naive time in America/Los_Angeles.
            # We must treat it as LA, then convert to NY (self.local_tz).
            if current_time.tzinfo is None:
                 current_time = current_time.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
            
            now_local = current_time.astimezone(self.local_tz)

            # sys.stdout.write(f"[NWS DEBUG TRACE] on_market_update: {ticker} | EngineTime={current_time} | LocalNY={now_local} | Orders={len(active_orders)}\n")
            # sys.stdout.flush()

            # 1. CLOCK GUARD: Is it time to trade?
            # We normally check this first to avoid noise.
            target_date = self._target_date_for_now(now_local)
            if target_date is None:
                self.last_gate_reason = "before_entry_time"
                return None
            
            # 2. OVERLAP GUARD: Do we have pending orders?
            if active_orders:
                self.last_gate_reason = "active_orders_present"
                return None

            # 3. DONE DATE GUARD: Did we already mark this as done?
            if target_date in self._done_target_dates:
                self.last_gate_reason = "already_traded_target_date"
                self._log(f"Status: Already traded for {target_date}", throttle=True, throttle_seconds=300)
                return None

            # ONE-SHOT GUARD: If we already have ANY position for this target, assume we are done.
            # This prevents "topping up" partial fills or double-dipping after a restart.
            # We check the 'inventory' passed by the engine (which includes global state now).
            # We need to find the ticker corresponding to this target_date to check inventory.
            # (We derived target_tickers earlier, but haven't filtered for the specific one yet).
            # A simple heuristic: check ALL tickers for this target_date.
            chk_tickers = [t for t, d in self._ticker_market_date.items() if d == target_date]
            for t in chk_tickers:
                inv = portfolios_inventories.get(t, {})
                # check if we have > 0 YES or NO
                y_qty = int(inv.get("yes") or 0)
                n_qty = int(inv.get("no") or 0)
                if y_qty > 0 or n_qty > 0:
                     self.last_gate_reason = "already_have_position"
                     self.last_gate_detail = f"ticker={t} yes={y_qty} no={n_qty}"
                     # Restore memory of being done nicely
                     self._done_target_dates.add(target_date)
                     return None

            # self._log(f"IT'S TIME! Analysis for target={target_date} (Now={now_local.time()})", throttle=True, throttle_seconds=60)
        except Exception as e:
            sys.stdout.write(f"[NWS CRASH] {e}\n")
            traceback.print_exc()
            sys.stdout.flush()
            return None



        target_tickers = [t for t, d in self._ticker_market_date.items() if d == target_date]
        if len(target_tickers) < self.min_markets_in_snapshot:
            self.last_gate_reason = "waiting_full_snapshot"
            self.last_gate_detail = (
                f"target_date={target_date.isoformat()} tickers={len(target_tickers)} "
                f"required={self.min_markets_in_snapshot}"
            )
            return None

        defs = self._build_contract_defs(target_tickers)
        if len(defs) < self.min_markets_in_snapshot:
            self.last_gate_reason = "contract_parse_incomplete"
            return None

        decision_anchor_local = self._decision_anchor_for_target(target_date=target_date, now_local=now_local)
        try:
            forecast_max, runtime_utc = self._resolve_forecast_for_target(
                target_day=target_date,
                decision_anchor_local=decision_anchor_local,
            )
        except Exception as exc:
            self.last_gate_reason = "forecast_fetch_error"
            self.last_gate_detail = str(exc)
            self._log(f"[ERROR] Forecast fetch failed: {exc}")
            return None

        if forecast_max is None:
            self.last_gate_reason = "no_forecast_found"
            self._log(f"Forecast MISSING for {target_date} (Runtime: {runtime_utc})", throttle=True, throttle_seconds=300)
            return None
        
        self._log(f"Using Forecast: {forecast_max} F (Runtime: {runtime_utc})")



        side, step = self._regime_params(forecast_max)
        target_ticker = self._step_ticker(forecast_max, defs, step)
        if target_ticker is None:
            self.last_gate_reason = "no_contract_for_step"
            self.last_gate_detail = f"forecast={forecast_max:.2f} step={step}"
            return None

        ask = self._latest_yes_ask.get(target_ticker) if side == "YES" else self._latest_no_ask.get(target_ticker)
        if ask is None:
            self.last_gate_reason = "missing_ask"
            self.last_gate_detail = target_ticker
            return None

        if side == "NO":
            if ask < self.min_no_ask:
                self.last_gate_reason = "no_ask_too_low"
                return None
            if ask > self.max_no_ask:
                self.last_gate_reason = "skip_day_no_ask_too_high"
                self.last_gate_detail = f"ask={ask:.2f} max={self.max_no_ask:.2f}"
                self._done_target_dates.add(target_date)
                return None

        est_equity = self._estimate_total_equity(float(cash), portfolios_inventories)
        target_exposure = est_equity * self.cash_fraction
        
        # Calculate current exposure for this target ticker
        current_inv = portfolios_inventories.get(target_ticker, {})
        current_yes = int(current_inv.get("yes") or 0)
        current_no = int(current_inv.get("no") or 0)
        
        # Value current position at market price (or cost basis if no quote, simplified here to market)
        # We only care about the side we want to Buy.
        # If we want to Buy NO, check NO exposure.
        current_exposure_dollars = 0.0
        if side == "NO":
             current_exposure_dollars = current_no * (float(ask) / 100.0) # Conservative: value at ask (replacement cost)
        else:
             current_exposure_dollars = current_yes * (float(ask) / 100.0)

        budget = min(float(cash), target_exposure - current_exposure_dollars)
        if budget <= 0:
            self.last_gate_reason = "max_exposure_reached"
            self.last_gate_detail = f"target=${target_exposure:.2f} current=${current_exposure_dollars:.2f}"
            return None

        p = float(ask) / 100.0
        fee_cents = 7.0 * p * (1.0 - p)
        est_cost_per_contract = max((float(ask) + fee_cents) / 100.0, 0.01)
        qty = int(math.floor(budget / est_cost_per_contract))
        if qty <= 0:
            self.last_gate_reason = "budget_too_small"
            self.last_gate_detail = f"cash={cash:.2f} est_equity={est_equity:.2f} ask={ask:.2f}"
            self._log(f"Trade Plan REJECTED: Budget too small (Qty=0). Cash={cash:.2f} TargetBudget={target_budget:.2f}")
            return None

        action = "BUY_YES" if side == "YES" else "BUY_NO"
        self._log(f"Trade Plan: {action} {qty}x {target_ticker} @ {self.market_order_price} (Anchor={self.decision_anchor_mode})")

        # REVERTED: Do NOT mark as done immediately.
        # We rely on the inventory check (at top of function) to stop us once filled.
        # This allows retries if the Engine/API fails to place the order.
        # self._done_target_dates.add(target_date)
        
        runtime_txt = runtime_utc.strftime("%Y-%m-%d %H:%M") if runtime_utc else "unknown"
        self.last_gate_reason = "trade"
        self.last_gate_detail = (
            f"target={target_date.isoformat()} forecast={forecast_max:.2f}F "
            f"runtime_utc={runtime_txt} mode={self.decision_anchor_mode} side={action} "
            f"step={step} ticker={target_ticker} ask={ask:.2f} est_equity={est_equity:.2f} "
            f"target_budget={target_exposure:.2f} spend_budget={budget:.2f}"
        )

        return [
            {
                "action": action,
                "ticker": target_ticker,
                "qty": qty,
                "price": self.market_order_price,
                "expiry": None,
                "source": "NWS_REGIME_F6_0322_EQ_TARGET",
            }
        ]


def champion_f6_0322_live_equity50(**kwargs):
    cfg = dict(kwargs)
    cfg.setdefault("name", "champion_f6_0322_live_equity50")
    cfg.setdefault("decision_anchor_mode", "rolling_latest")
    cfg.setdefault("forecast_delay_minutes", 0)
    cfg.setdefault("cash_fraction", 0.5)
    return NWSRegimeSplitF60322EquityTargetTrader(**cfg)


def champion_live_current(**kwargs):
    """
    Current champion:
    - F6_0322 regime logic
    - Rolling latest forecast
    - No synthetic forecast delay
    - Size toward 50% of total equity, capped by available cash
    """
    cfg = dict(kwargs)
    cfg.setdefault("name", "champion_live_current")
    cfg.setdefault("decision_anchor_mode", "rolling_latest")
    cfg.setdefault("forecast_delay_minutes", 0)
    cfg.setdefault("cash_fraction", 0.5)
    return NWSRegimeSplitF60322EquityTargetTrader(**cfg)
