from __future__ import annotations

import json
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


class NWSRegimeSplitF60322Trader:
    """
    Champion strategy from fine-tuning (F6_0322):
    - Entry: day-before 17:00 local
    - Forecast source: NAM MOS at decision anchor minus 171 minutes
    - Regimes:
      * forecast < t1       -> NO at step_cold (-2)
      * t1 <= forecast < t2 -> NO at step_mid  (0)
      * forecast >= t2      -> NO at step_hot  (0)
    - Ask filter: no_ask <= max_no_ask
    - Sizing: spend cash_fraction of available cash
    - One trade per target market date
    """

    def __init__(
        self,
        *,
        name: str = "nws_regime_split_f6_0322",
        local_timezone: str = "America/New_York",
        model: str = "NAM",
        mos_station: str = "KNYC",
        runtime_step_hours: int = 6,
        runtime_backtrack_hours: int = 72,
        forecast_delay_minutes: int = 171,
        entry_time: str = "17:00",
        # Tuned params (F6_0322)
        t1: float = 36.90630939900468,
        t2: float = 64.2172272554991,
        step_cold: int = -2,
        step_mid: int = 0,
        step_hot: int = 0,
        side_cold: str = "NO",
        side_mid: str = "NO",
        side_hot: str = "NO",
        cash_fraction: float = 0.5,
        market_order_price: int = 99,
        min_no_ask: float = 1.0,
        max_no_ask: float = 91.32454360553209,
        min_markets_in_snapshot: int = 6,
        http_timeout_seconds: int = 20,
    ) -> None:
        self.name = name
        self.local_tz = ZoneInfo(local_timezone)
        self.model = model
        self.mos_station = mos_station
        self.runtime_step_hours = max(1, int(runtime_step_hours))
        self.runtime_backtrack_hours = max(self.runtime_step_hours, int(runtime_backtrack_hours))
        self.forecast_delay_minutes = max(0, int(forecast_delay_minutes))
        self.entry_time = self._parse_hhmm(entry_time)

        self.t1 = float(t1)
        self.t2 = float(t2)
        if self.t2 <= self.t1:
            raise ValueError("t2 must be greater than t1")

        self.step_cold = int(step_cold)
        self.step_mid = int(step_mid)
        self.step_hot = int(step_hot)
        self.side_cold = self._validate_side(side_cold)
        self.side_mid = self._validate_side(side_mid)
        self.side_hot = self._validate_side(side_hot)

        self.cash_fraction = max(0.0, min(1.0, float(cash_fraction)))
        self.market_order_price = max(1, min(99, int(market_order_price)))
        self.min_no_ask = float(min_no_ask)
        self.max_no_ask = float(max_no_ask)
        self.min_markets_in_snapshot = max(1, int(min_markets_in_snapshot))
        self.http_timeout_seconds = max(1, int(http_timeout_seconds))

        self._latest_yes_ask: dict[str, float] = {}
        self._latest_no_ask: dict[str, float] = {}
        self._ticker_market_date: dict[str, date] = {}
        self._done_target_dates: set[date] = set()
        self._runtime_cache: dict[str, list[dict] | None] = {}
        self._forecast_cache: dict[tuple[date, str], tuple[float | None, datetime | None]] = {}

        self.last_gate_reason = None
        self.last_gate_detail = None
        self._last_log_msg: str | None = None
        self._last_log_ts: float = 0.0

    def _log(self, msg: str, throttle: bool = False, throttle_seconds: int = 60):
        import time
        now = time.time()
        
        if throttle:
            if msg == self._last_log_msg and (now - self._last_log_ts) < throttle_seconds:
                return
        elif msg == self._last_log_msg:
             # Default deduplication for non-throttled messages
             return

        print(f"[NWS] {msg}")
        self._last_log_msg = msg
        self._last_log_ts = now

    def _parse_hhmm(self, value: str) -> time:
        raw = (value or "").strip()
        if ":" not in raw:
            if len(raw) != 4:
                raise ValueError(f"Invalid HH:MM time: {value!r}")
            raw = f"{raw[:2]}:{raw[2:]}"
        hh_txt, mm_txt = raw.split(":", 1)
        hh = int(hh_txt)
        mm = int(mm_txt)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError(f"Invalid HH:MM time: {value!r}")
        return time(hour=hh, minute=mm)

    def _validate_side(self, side: str) -> str:
        s = (side or "").strip().upper()
        if s not in {"YES", "NO"}:
            raise ValueError(f"Invalid side {side!r}; expected YES or NO")
        return s

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
        # FIX: Do not cache None (404/failure). Allow retry on next tick.
        if rows is not None:
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

    def _resolve_forecast_for_target(
        self,
        *,
        target_day: date,
        decision_anchor_local: datetime,
    ) -> tuple[float | None, datetime | None]:
        cache_key = (target_day, decision_anchor_local.strftime("%Y-%m-%d %H:%M"))
        if cache_key in self._forecast_cache:
            return self._forecast_cache[cache_key]

        decision_utc = decision_anchor_local.astimezone(UTC) - timedelta(minutes=self.forecast_delay_minutes)
        runtime_utc = self._floor_runtime(decision_utc)
        steps = int(self.runtime_backtrack_hours / self.runtime_step_hours) + 1

        chosen_rows = None
        chosen_runtime = None
        for _ in range(steps):
            rows = self._fetch_mos_runtime(runtime_utc)
            if rows:
                chosen_rows = rows
                chosen_runtime = runtime_utc
                break
            runtime_utc -= timedelta(hours=self.runtime_step_hours)

        if chosen_rows is None:
            result = (None, None)
        else:
            result = (self._forecast_max_for_day_from_run(chosen_rows, target_day), chosen_runtime)

        if result[0] is not None:
            self._forecast_cache[cache_key] = result
        return result

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
                continue
            if low_tail_marker is not None and value == low_tail_marker:
                defs[ticker] = ContractDef(ticker=ticker, low=None, high=low_tail_upper)
            elif high_tail_marker is not None and value == high_tail_marker:
                defs[ticker] = ContractDef(ticker=ticker, low=high_tail_lower, high=None)
        return defs

    def _contract_center(self, contract: ContractDef) -> float:
        if contract.low is None and contract.high is not None:
            return float(contract.high) - 1.0
        if contract.high is None and contract.low is not None:
            return float(contract.low) + 1.0
        if contract.low is not None and contract.high is not None:
            return (float(contract.low) + float(contract.high)) / 2.0
        return 0.0

    def _ordered_tickers(self, defs: dict[str, ContractDef]) -> list[str]:
        return [t for t, _ in sorted(defs.items(), key=lambda kv: self._contract_center(kv[1]))]

    def _find_contract_for_temp(self, temp_f: float, defs: dict[str, ContractDef]) -> str | None:
        t = int(round(float(temp_f)))
        for tkr, c in defs.items():
            lo = -10_000 if c.low is None else c.low
            hi = 10_000 if c.high is None else c.high
            if lo <= t <= hi:
                return tkr
        return None

    def _step_ticker(self, forecast: float, defs: dict[str, ContractDef], step: int) -> str | None:
        base = self._find_contract_for_temp(forecast, defs)
        if base is None:
            return None
        ordered = self._ordered_tickers(defs)
        try:
            idx = ordered.index(base)
        except ValueError:
            return None
        j = idx + int(step)
        if j < 0 or j >= len(ordered):
            return None
        return ordered[j]

    def _target_date_for_now(self, now_local: datetime) -> date | None:
        if now_local.time() >= self.entry_time:
            return now_local.date() + timedelta(days=1)
        return None

    def _regime_params(self, forecast: float) -> tuple[str, int]:
        if forecast < self.t1:
            return self.side_cold, self.step_cold
        if forecast < self.t2:
            return self.side_mid, self.step_mid
        return self.side_hot, self.step_hot

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

        yes_ask = market_state.get("yes_ask")
        no_ask = market_state.get("no_ask")
        if yes_ask is not None:
            self._latest_yes_ask[ticker] = float(yes_ask)
        if no_ask is not None:
            self._latest_no_ask[ticker] = float(no_ask)

        if active_orders:
            self.last_gate_reason = "active_orders_present"
            return None

        try:
            # Fix timezone handling: use astimezone to convert system local time (e.g. PST) to target (NY)
            # .replace() blindly treats naive PST as NY time (3h lag). .astimezone() converts it.
            now_local = current_time.astimezone(self.local_tz)
                
            target_date = self._target_date_for_now(now_local)
        except Exception as e:
            import traceback
            print(f"[ERROR] Date conversion failed: {e}\n{traceback.format_exc()}")
            self.last_gate_reason = "date_conversion_error"
            return None
        if target_date is None:
            self.last_gate_reason = "before_entry_time"
            self._log(f"Status: Waiting for {self.entry_time} {self.local_tz} (Current: {now_local.strftime('%H:%M')})", throttle=True, throttle_seconds=300)
            return None
        if target_date in self._done_target_dates:
            self.last_gate_reason = "already_traded_target_date"
            self._log(f"Status: Already traded for {target_date}", throttle=True, throttle_seconds=300)
            return None

        target_tickers = [t for t, d in self._ticker_market_date.items() if d == target_date]
        if len(target_tickers) < self.min_markets_in_snapshot:
            self.last_gate_reason = "waiting_full_snapshot"
            self.last_gate_detail = (
                f"target_date={target_date.isoformat()} tickers={len(target_tickers)} "
                f"required={self.min_markets_in_snapshot}"
            )
            self._log(f"Status: Waiting for full snapshot: {len(target_tickers)}/{self.min_markets_in_snapshot} tickers found for {target_date}", throttle=True, throttle_seconds=300)
            return None
            
        self._log(f"IT'S TIME! Target Date: {target_date} | Entries: {len(target_tickers)}")

        defs = self._build_contract_defs(target_tickers)
        if len(defs) < self.min_markets_in_snapshot:
            self.last_gate_reason = "contract_parse_incomplete"
            self._log("Status: Contract parsing incomplete", throttle=True, throttle_seconds=300)
            return None

        # Anchor decision time to exact day-before entry boundary, not current tick,
        # so this matches backtest semantics.
        decision_anchor_local = datetime.combine(target_date - timedelta(days=1), self.entry_time, tzinfo=self.local_tz)

        self._log(f"CHECKING FORECAST for {target_date} (Anchor: {decision_anchor_local})")

        try:
            forecast_max, runtime_utc = self._resolve_forecast_for_target(
                target_day=target_date,
                decision_anchor_local=decision_anchor_local,
            )
        except Exception as exc:
            self.last_gate_reason = "forecast_fetch_error"
            self.last_gate_detail = str(exc)
            self._log(f"Status: Forecast fetch error: {exc}", throttle=True, throttle_seconds=300)
            return None

        if forecast_max is None:
            self.last_gate_reason = "no_forecast_found"
            self._log(f"Status: Forecast MISSING for {target_date} (Runtime: {runtime_utc})", throttle=True, throttle_seconds=300)
            return None
            
        self._log(f"FOUND FORECAST: {forecast_max:.2f}F (Runtime: {runtime_utc})")

        side, step = self._regime_params(forecast_max)
        target_ticker = self._step_ticker(forecast_max, defs, step)
        if target_ticker is None:
            self.last_gate_reason = "no_contract_for_step"
            self.last_gate_detail = f"forecast={forecast_max:.2f} step={step}"
            self._log(f"Status: No contract found for Forecast={forecast_max:.2f} Step={step}", throttle=True, throttle_seconds=300)
            return None

        ask = self._latest_yes_ask.get(target_ticker) if side == "YES" else self._latest_no_ask.get(target_ticker)
        if ask is None:
            self.last_gate_reason = "missing_ask"
            self.last_gate_detail = target_ticker
            self._log(f"Status: Missing Ask Price for {target_ticker}", throttle=True, throttle_seconds=300)
            return None

        # NO-focused tuned strategy, but keep side generic for completeness.
        if side == "NO":
            if ask < self.min_no_ask:
                self.last_gate_reason = "no_ask_too_low"
                self._log(f"Ask too low for {target_ticker}: {ask:.2f} < {self.min_no_ask:.2f}")
                return None
            if ask > self.max_no_ask:
                self.last_gate_reason = "skip_day_no_ask_too_high"
                self.last_gate_detail = f"ask={ask:.2f} max={self.max_no_ask:.2f}"
                self._log(f"Ask too high for {target_ticker}: {ask:.2f} > {self.max_no_ask:.2f}")
                self._done_target_dates.add(target_date)
                return None

        budget = float(cash) * self.cash_fraction
        if budget <= 0:
            self.last_gate_reason = "no_cash_budget"
            self._log(f"No cash budget: Cash=${cash:.2f}")
            return None

        p = float(ask) / 100.0
        fee_cents = 7.0 * p * (1.0 - p)
        est_cost_per_contract = max((float(ask) + fee_cents) / 100.0, 0.01)
        qty = int(math.floor(budget / est_cost_per_contract))
        if qty <= 0:
            self.last_gate_reason = "budget_too_small"
            self.last_gate_detail = f"cash={cash:.2f} ask={ask:.2f} budget=${budget:.2f} cost=${est_cost_per_contract:.2f}"
            self._log(f"Budget too small: Cash=${cash:.2f} Budget=${budget:.2f} Ask={ask:.2f} Qty={qty}")
            return None

        self._log(f"TRYING TO PLACE BETS ON: {target_ticker} (Qty: {qty}, Price: {self.market_order_price}, Side: {side})")

        action = "BUY_YES" if side == "YES" else "BUY_NO"
        self._done_target_dates.add(target_date)
        runtime_txt = runtime_utc.strftime("%Y-%m-%d %H:%M") if runtime_utc else "unknown"
        self.last_gate_reason = "trade"
        self.last_gate_detail = (
            f"target={target_date.isoformat()} forecast={forecast_max:.2f}F "
            f"runtime_utc={runtime_txt} side={action} step={step} ticker={target_ticker} ask={ask:.2f}"
        )

        return [
            {
                "action": action,
                "ticker": target_ticker,
                "qty": qty,
                "price": self.market_order_price,
                "expiry": None,
                "source": "NWS_REGIME_F6_0322",
            }
        ]


def nws_regime_split_f6_0322(**kwargs):
    kwargs = dict(kwargs)
    kwargs.setdefault("name", "nws_regime_split_f6_0322")
    return NWSRegimeSplitF60322Trader(**kwargs)


def nws_regime_split_f6_0322_cash50(**kwargs):
    kwargs = dict(kwargs)
    kwargs.setdefault("name", "nws_regime_split_f6_0322_cash50")
    kwargs.setdefault("cash_fraction", 0.5)
    return NWSRegimeSplitF60322Trader(**kwargs)
