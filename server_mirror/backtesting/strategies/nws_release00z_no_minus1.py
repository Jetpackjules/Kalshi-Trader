from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from backtesting.engine import parse_market_date_from_ticker


MOS_API_URL = "https://mesonet.agron.iastate.edu/api/1/mos.json"


@dataclass(frozen=True)
class ContractDef:
    ticker: str
    low: Optional[int]
    high: Optional[int]


class NWSRelease00ZNoMinus1Trader:
    """
    Dedicated strategy:
    - Wait for release_00z forecast availability for a market date.
    - Take forecast max temp for that market date.
    - Buy NO on the contract at (forecast - 1F) bucket.
    - Spend a fixed fraction of available cash (default 50%).
    - Place at most one trade per target market date.
    """

    def __init__(
        self,
        *,
        name: str = "nws_release00z_no_minus1",
        local_timezone: str = "America/New_York",
        model: str = "NAM",
        mos_station: str = "KNYC",
        runtime_step_hours: int = 6,
        runtime_backtrack_hours: int = 72,
        cash_fraction: float = 0.5,
        market_order_price: int = 99,
        min_no_ask: float = 1.0,
        max_no_ask: float = 90.0,
        min_markets_in_snapshot: int = 6,
        http_timeout_seconds: int = 20,
    ) -> None:
        self.name = name
        self.local_tz = ZoneInfo(local_timezone)
        self.model = model
        self.mos_station = mos_station
        self.runtime_step_hours = max(1, int(runtime_step_hours))
        self.runtime_backtrack_hours = max(self.runtime_step_hours, int(runtime_backtrack_hours))
        self.cash_fraction = max(0.0, min(1.0, float(cash_fraction)))
        self.market_order_price = max(1, min(99, int(market_order_price)))
        self.min_no_ask = float(min_no_ask)
        self.max_no_ask = float(max_no_ask)
        self.min_markets_in_snapshot = max(1, int(min_markets_in_snapshot))
        self.http_timeout_seconds = max(1, int(http_timeout_seconds))

        self._latest_no_ask: dict[str, float] = {}
        self._ticker_market_date: dict[str, date] = {}
        self._done_target_dates: set[date] = set()
        self._runtime_cache: dict[str, list[dict] | None] = {}
        self._forecast_cache: dict[date, tuple[float | None, datetime | None]] = {}

        self.last_gate_reason = None
        self.last_gate_detail = None

    def _http_get_json(self, url: str, params: dict[str, str]) -> dict:
        full_url = f"{url}?{urlencode(params)}"
        try:
            with urlopen(full_url, timeout=self.http_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                raise
            raise RuntimeError(f"HTTP {exc.code} for {full_url}") from exc
        except URLError as exc:
            raise RuntimeError(f"Request failed for {full_url}: {exc}") from exc

    def _parse_utc_timestamp(self, ts: str) -> datetime:
        if "T" in ts:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        return datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)

    def _floor_runtime(self, dt_utc: datetime) -> datetime:
        dt_utc = dt_utc.replace(minute=0, second=0, microsecond=0)
        step = self.runtime_step_hours
        hour = dt_utc.hour - (dt_utc.hour % step)
        return dt_utc.replace(hour=hour)

    def _fetch_mos_runtime(self, runtime_utc: datetime) -> list[dict] | None:
        key = runtime_utc.strftime("%Y-%m-%d %H:%M")
        if key in self._runtime_cache:
            return self._runtime_cache[key]
        params = {
            "station": self.mos_station,
            "model": self.model,
            "runtime": key,
        }
        try:
            payload = self._http_get_json(MOS_API_URL, params)
            rows = payload.get("data", []) or None
        except HTTPError as exc:
            if exc.code == 404:
                rows = None
            else:
                raise
        self._runtime_cache[key] = rows
        return rows

    def _forecast_max_for_day_from_run(self, run_rows: list[dict], target_day: date) -> float | None:
        max_tmp = None
        for row in run_rows:
            tmp = row.get("tmp")
            ftime = row.get("ftime")
            if tmp in ("", None) or ftime in ("", None):
                continue
            try:
                temp = float(tmp)
                forecast_time_utc = self._parse_utc_timestamp(str(ftime))
            except ValueError:
                continue
            if forecast_time_utc.astimezone(self.local_tz).date() != target_day:
                continue
            if max_tmp is None or temp > max_tmp:
                max_tmp = temp
        return max_tmp

    def _release_00z_local_for_target(self, target_day: date) -> datetime:
        # release_00z decision boundary: target_day at 00:05 UTC.
        return datetime.combine(target_day, time(0, 5), tzinfo=UTC).astimezone(self.local_tz)

    def _resolve_forecast_release_00z(self, target_day: date) -> tuple[float | None, datetime | None]:
        if target_day in self._forecast_cache:
            # Check if we have a valid cached result (not None)
            # If we previously cached a None result, we should RETRY (handled by not returning here if value is None)
            cached_val = self._forecast_cache[target_day]
            if cached_val[0] is not None:
                return cached_val

        # decision_utc is 00:05 UTC on target day.
        # The 00Z run "belongs" to this day (released at 00:00).
        decision_utc = datetime.combine(target_day, time(0, 5), tzinfo=UTC)
        runtime_utc = self._floor_runtime(decision_utc)
        
        # Backtracking Logic: Try current runtime, then step back by 6 hours until found or limit reached.
        # This allows us to trade at 7 PM EST (00Z) even if the 00Z forecast hasn't published yet (using 18Z or 12Z).
        limit_hours = self.runtime_backtrack_hours
        step_hours = self.runtime_step_hours
        
        chosen_rows = None
        chosen_runtime = None

        for offset in range(0, limit_hours + 1, step_hours):
            test_runtime = runtime_utc - timedelta(hours=offset)
            rows = self._fetch_mos_runtime(test_runtime)
            if rows:
                chosen_rows = rows
                chosen_runtime = test_runtime
                break
        
        if chosen_rows:
            # We found it! Cache it forever.
            max_temp = self._forecast_max_for_day_from_run(chosen_rows, target_day)
            result = (max_temp, chosen_runtime)
            self._forecast_cache[target_day] = result
            logging.info(f"[NWS] Cached Forecast for {target_day}: Max={max_temp}F (Runtime: {chosen_runtime})")
            return result
        else:
            # Not found yet for any recent run.
            return (None, None)

    def _parse_suffix(self, ticker: str) -> tuple[str, float] | None:
        suffix = ticker.split("-")[-1]
        if not suffix or suffix[0] not in {"B", "T"}:
            return None
        try:
            return suffix[0], float(suffix[1:])
        except ValueError:
            return None

    def _build_contract_defs(self, tickers: list[str]) -> dict[str, ContractDef]:
        parsed = []
        for t in sorted(set(tickers)):
            s = self._parse_suffix(t)
            if s is not None:
                kind, value = s
                parsed.append((t, kind, value))
        b_values = [v for _, k, v in parsed if k == "B"]
        t_values = [v for _, k, v in parsed if k == "T"]
        defs: dict[str, ContractDef] = {}
        if not b_values:
            return defs

        b_min_low = int(math.floor(min(b_values)))
        b_max_high = int(math.ceil(max(b_values)))
        low_tail_upper = b_min_low - 1
        high_tail_lower = b_max_high + 1
        low_tail_marker = min(t_values) if t_values else None
        high_tail_marker = max(t_values) if t_values else None

        for ticker, kind, value in parsed:
            if kind == "B":
                defs[ticker] = ContractDef(
                    ticker=ticker,
                    low=int(math.floor(value)),
                    high=int(math.ceil(value)),
                )
            elif low_tail_marker is not None and value == low_tail_marker:
                defs[ticker] = ContractDef(ticker=ticker, low=None, high=low_tail_upper)
            elif high_tail_marker is not None and value == high_tail_marker:
                defs[ticker] = ContractDef(ticker=ticker, low=high_tail_lower, high=None)
        return defs

    def _find_contract_for_temp(self, temp_f: float, defs: dict[str, ContractDef]) -> str | None:
        # Pick contract that covers nearest integer temp to mirror settlement buckets.
        t = int(round(float(temp_f)))
        for tkr, c in defs.items():
            lo = -10_000 if c.low is None else c.low
            hi = 10_000 if c.high is None else c.high
            if lo <= t <= hi:
                return tkr
        return None

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

        no_ask = market_state.get("no_ask")
        if no_ask is not None:
            self._latest_no_ask[ticker] = float(no_ask)

        if active_orders:
            self.last_gate_reason = "active_orders_present"
            return None

        if current_time.tzinfo is None:
            now_local = current_time.replace(tzinfo=self.local_tz)
        else:
            now_local = current_time.astimezone(self.local_tz)
        candidates = sorted(set(self._ticker_market_date.values()))
        for target_date in candidates:
            if target_date in self._done_target_dates:
                continue
            release_local = self._release_00z_local_for_target(target_date)
            if now_local < release_local:
                continue

            # --- FIX: Strict 10-minute Window & Next Day Logic ---
            # --- FIX: Strict 2-hour Window & Next Day Logic ---
            # 1. We ONLY trade in the 2 hours following the release.
            # This prevents trading "stale" forecasts later in the day/next day.
            # It also implicitly enforces "Next Day" trading because the window for "Today"
            # would have closed yesterday evening.
            window_minutes = 120
            window_end = release_local + timedelta(minutes=window_minutes)
            if now_local > window_end:
                # We are past the window for this target date.
                self.last_gate_reason = "window_expired"
                self.last_gate_detail = f"now={now_local.isoformat()} > end={window_end.isoformat()}"
                self._done_target_dates.add(target_date) # Skip this date entirely
                continue
            # -----------------------------------------------------

            target_tickers = [t for t, d in self._ticker_market_date.items() if d == target_date]
            if len(target_tickers) < self.min_markets_in_snapshot:
                self.last_gate_reason = "waiting_full_snapshot"
                self.last_gate_detail = (
                    f"target_date={target_date.isoformat()} tickers={len(target_tickers)} "
                    f"required={self.min_markets_in_snapshot}"
                )
                continue

            defs = self._build_contract_defs(target_tickers)
            if len(defs) < self.min_markets_in_snapshot:
                self.last_gate_reason = "contract_parse_incomplete"
                continue

            try:
                forecast_max, runtime_utc = self._resolve_forecast_release_00z(target_date)
            except Exception as exc:
                self.last_gate_reason = "forecast_fetch_error"
                self.last_gate_detail = str(exc)
                continue
            if forecast_max is None:
                self.last_gate_reason = "no_forecast_found"
                continue

            target_ticker = self._find_contract_for_temp(forecast_max - 1.0, defs)
            if target_ticker is None:
                self.last_gate_reason = "no_contract_for_forecast_minus1"
                self.last_gate_detail = f"forecast={forecast_max:.2f}"
                continue

            ask = self._latest_no_ask.get(target_ticker)
            if ask is None:
                self.last_gate_reason = "missing_no_ask"
                self.last_gate_detail = target_ticker
                continue
            if ask > self.max_no_ask:
                # Explicitly skip this target day and move on.
                self.last_gate_reason = "skip_day_no_ask_too_high"
                self.last_gate_detail = (
                    f"target={target_date.isoformat()} ask={ask:.2f} max={self.max_no_ask:.2f}"
                )
                self._done_target_dates.add(target_date)
                continue
            if ask < self.min_no_ask:
                self.last_gate_reason = "no_ask_too_low"
                self.last_gate_detail = f"{ask:.2f}"
                continue


            # --- FIX: Check for existing position or active orders to prevent double-trading on restart ---
            # Check active orders for this ticker
            if active_orders:
                # The engine passes ALL active orders for the strategy?
                # Usually `active_orders` arg is a list of orders.
                # Let's filter for this ticker.
                ticker_orders = [o for o in active_orders if o['ticker'] == target_ticker]
                if ticker_orders:
                    self.last_gate_reason = "active_order_exists"
                    self.last_gate_detail = f"{len(ticker_orders)} orders"
                    self._done_target_dates.add(target_date) # Mark as done so we don't check again
                    continue

            # Check portfolio inventory
            pos = portfolios_inventories.get(target_ticker, {})
            # 'pos' structure: {'yes': 0, 'no': 10, ...}
            if pos.get('yes', 0) > 0 or pos.get('no', 0) > 0:
                self.last_gate_reason = "position_exists"
                self.last_gate_detail = f"yes={pos.get('yes')} no={pos.get('no')}"
                self._done_target_dates.add(target_date) # Mark as done
                continue
            # --------------------------------------------------------------------------------------------

            budget = float(cash) * self.cash_fraction
            if budget <= 0:
                self.last_gate_reason = "no_cash_budget"
                continue

            p = ask / 100.0
            fee_cents = 7.0 * p * (1.0 - p)
            est_cost_per_contract = max((ask + fee_cents) / 100.0, 0.01)
            qty = int(math.floor(budget / est_cost_per_contract))
            if qty <= 0:
                self.last_gate_reason = "budget_too_small"
                self.last_gate_detail = f"cash={cash:.2f} ask={ask:.2f}"
                continue

            self._done_target_dates.add(target_date)
            runtime_txt = runtime_utc.strftime("%Y-%m-%d %H:%M") if runtime_utc else "unknown"
            self.last_gate_reason = "trade"
            self.last_gate_detail = (
                f"target={target_date.isoformat()} forecast={forecast_max:.2f}F runtime_utc={runtime_txt} "
                f"ticker={target_ticker} side=BUY_NO ask={ask:.2f}"
            )
            logging.info(f"[NWS] EXECUTING TRADE: {self.last_gate_detail} | Budget: {qty} contracts @ {self.market_order_price}")
            return [
                {
                    "action": "BUY_NO",
                    "ticker": target_ticker,
                    "qty": qty,
                    "price": self.market_order_price,
                    "expiry": None,
                    "source": "NWS_00Z_M1",
                }
            ]

        self.last_gate_reason = "before_release_or_no_target"
        return None


def nws_release00z_no_minus1(**kwargs):
    kwargs = dict(kwargs)
    kwargs.setdefault("name", "nws_release00z_no_minus1")
    return NWSRelease00ZNoMinus1Trader(**kwargs)


def nws_release00z_no_minus1_cash50(**kwargs):
    kwargs = dict(kwargs)
    kwargs.setdefault("name", "nws_release00z_no_minus1_cash50")
    kwargs.setdefault("cash_fraction", 0.5)
    return NWSRelease00ZNoMinus1Trader(**kwargs)
