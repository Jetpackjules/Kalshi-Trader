from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


def _build_market_state(row: dict) -> dict:
    return {
        "yes_ask": row.get("yes_ask"),
        "no_ask": row.get("no_ask"),
        "yes_bid": row.get("yes_bid"),
        "no_bid": row.get("no_bid"),
    }


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_time(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _row_to_tick(row: dict, ts_col: str) -> dict | None:
    ts = _parse_time(row.get(ts_col))
    if ts is None:
        return None
    return {
        "time": ts,
        "ticker": row.get("ticker"),
        "market_state": _build_market_state(
            {
                "yes_ask": _parse_float(row.get("yes_ask")),
                "no_ask": _parse_float(row.get("no_ask")),
                "yes_bid": _parse_float(row.get("yes_bid")),
                "no_bid": _parse_float(row.get("no_bid")),
            }
        ),
    }


def iter_ticks_from_market_logs(
    log_dir: str,
    *,
    follow: bool = False,
    poll_s: float = 0.5,
    diag_log=None,
    heartbeat_s: float = 30.0,
) -> Iterable[dict]:
    log_path = Path(log_dir)
    if not follow:
        files = sorted(log_path.glob("market_data_*.csv"))
        frames = []
        for path in files:
            df = pd.read_csv(path)
            if df.empty:
                continue
            df = df.rename(
                columns={
                    "timestamp": "time",
                    "market_ticker": "ticker",
                    "implied_yes_ask": "yes_ask",
                    "implied_no_ask": "no_ask",
                    "best_yes_bid": "yes_bid",
                    "best_no_bid": "no_bid",
                }
            )
            frames.append(df[["time", "ticker", "yes_ask", "no_ask", "yes_bid", "no_bid"]])
        if not frames:
            return []
        data = pd.concat(frames, ignore_index=True)
        data["time"] = pd.to_datetime(data["time"], errors="coerce", format="mixed")
        data = data.dropna(subset=["time"])
        data = data.sort_values("time")
        for row in data.itertuples(index=False):
            tick = {
                "time": row.time,
                "ticker": row.ticker,
                "market_state": _build_market_state(
                    {
                        "yes_ask": row.yes_ask,
                        "no_ask": row.no_ask,
                        "yes_bid": row.yes_bid,
                        "no_bid": row.no_bid,
                    }
                ),
            }
            yield tick
        return []

    file_offsets: dict[Path, int] = {}
    file_headers: dict[Path, list[str]] = {}
    last_tick_ts: datetime | None = None
    last_heartbeat = time.time()

    def _init_file(path: Path) -> None:
        with path.open("r", newline="") as handle:
            header_line = handle.readline()
            if not header_line:
                return
            file_headers[path] = [h.strip() for h in header_line.strip().split(",")]
            handle.seek(0, os.SEEK_END)
            file_offsets[path] = handle.tell()

    while True:
        files = sorted(log_path.glob("market_data_*.csv"))
        for path in files:
            if path not in file_offsets:
                _init_file(path)
                continue
            with path.open("r", newline="") as handle:
                handle.seek(file_offsets[path])
                reader = csv.DictReader(handle, fieldnames=file_headers[path])
                for row in reader:
                    normalized = {
                        "timestamp": row.get("timestamp"),
                        "ticker": row.get("market_ticker"),
                        "yes_ask": row.get("implied_yes_ask"),
                        "no_ask": row.get("implied_no_ask"),
                        "yes_bid": row.get("best_yes_bid"),
                        "no_bid": row.get("best_no_bid"),
                    }
                    tick = _row_to_tick(normalized, "timestamp")
                    if tick:
                        last_tick_ts = tick["time"]
                        yield tick
                file_offsets[path] = handle.tell()
        now = time.time()
        if diag_log and (now - last_heartbeat) >= heartbeat_s:
            diag_log("FOLLOW_WAIT", tick_ts=last_tick_ts, source="market_logs")
            last_heartbeat = now
        time.sleep(poll_s)


def iter_ticks_from_live_log(
    path: str,
    *,
    use_ingest: bool = False,
    follow: bool = False,
    poll_s: float = 0.5,
    diag_log=None,
    heartbeat_s: float = 30.0,
) -> Iterable[dict]:
    if follow:
        log_path = Path(path)
        last_tick_ts: datetime | None = None
        last_heartbeat = time.time()
        while not log_path.exists():
            if diag_log and (time.time() - last_heartbeat) >= heartbeat_s:
                diag_log("FOLLOW_WAIT", tick_ts=last_tick_ts, source="live_log")
                last_heartbeat = time.time()
            time.sleep(poll_s)

        with log_path.open("r", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            if not fieldnames:
                return []
            if "tick_timestamp" in fieldnames:
                ts_col = "ingest_timestamp" if use_ingest else "tick_timestamp"
            else:
                ts_col = "timestamp"

            for row in reader:
                tick = _row_to_tick(row, ts_col)
                if tick:
                    last_tick_ts = tick["time"]
                    yield tick

            while True:
                position = handle.tell()
                line = handle.readline()
                if not line:
                    now = time.time()
                    if diag_log and (now - last_heartbeat) >= heartbeat_s:
                        diag_log("FOLLOW_WAIT", tick_ts=last_tick_ts, source="live_log")
                        last_heartbeat = now
                    time.sleep(poll_s)
                    handle.seek(position)
                    continue
                row = next(csv.DictReader([line], fieldnames=fieldnames))
                if row.get(ts_col) in (None, "", ts_col):
                    continue
                tick = _row_to_tick(row, ts_col)
                if tick:
                    last_tick_ts = tick["time"]
                    yield tick
        return []

    df = pd.read_csv(path)
    if df.empty:
        return []
    if "tick_timestamp" in df.columns:
        ts_col = "ingest_timestamp" if use_ingest else "tick_timestamp"
    else:
        ts_col = "timestamp"
    df = df.rename(columns={ts_col: "time"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time")
    for row in df.itertuples(index=False):
        tick = {
            "time": row.time,
            "ticker": row.ticker,
            "market_state": _build_market_state(
                {
                    "yes_ask": row.yes_ask,
                    "no_ask": row.no_ask,
                    "yes_bid": row.yes_bid,
                    "no_bid": row.no_bid,
                }
            ),
        }
        yield tick
