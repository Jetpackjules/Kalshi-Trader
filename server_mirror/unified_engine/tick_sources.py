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


def _peek_file_time_bounds(path: Path) -> tuple[datetime | None, datetime | None]:
    earliest = None
    latest = None
    try:
        with path.open("r", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                earliest = _parse_time(row.get("timestamp"))
                break
    except OSError:
        pass

    try:
        with path.open("rb") as handle:
            try:
                handle.seek(-2048, os.SEEK_END)
            except OSError:
                handle.seek(0)
            tail = handle.read().decode("utf-8", errors="ignore").splitlines()
        for line in reversed(tail):
            if not line.strip():
                continue
            ts_raw = line.split(",", 1)[0]
            latest = _parse_time(ts_raw)
            if latest:
                break
    except OSError:
        pass

    return earliest, latest


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
        "seq": None,
        "source_file": row.get("source_file"),
        "source_row": row.get("source_row"),
    }


def iter_ticks_from_market_logs(
    log_dir: str,
    *,
    follow: bool = False,
    poll_s: float = 0.5,
    diag_log=None,
    heartbeat_s: float = 30.0,
    ingest_log=None,
    skip_file: str | None = None,
    skip_rows: int = 0,
) -> Iterable[dict]:
    log_path = Path(log_dir)
    if not follow:
        files = sorted(log_path.glob("market_data_*.csv"))
        rows = []
        for file_idx, path in enumerate(files):
            try:
                with path.open("r", newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames:
                        continue
                    for row_idx, row in enumerate(reader):
                        if skip_rows > 0 and skip_file and skip_file in path.name:
                            if row_idx < skip_rows:
                                continue
                        ts = _parse_time(row.get("timestamp"))
                        if ts is None:
                            continue
                        rows.append(
                            {
                                "time": ts,
                                "ticker": row.get("market_ticker"),
                                "yes_ask": _parse_float(row.get("implied_yes_ask")),
                                "no_ask": _parse_float(row.get("implied_no_ask")),
                                "yes_bid": _parse_float(row.get("best_yes_bid")),
                                "no_bid": _parse_float(row.get("best_no_bid")),
                                "source_file": path.name,
                                "source_order": file_idx,
                                "source_row": row_idx,
                            }
                        )
            except OSError:
                continue
        if not rows:
            return []
        rows.sort(key=lambda r: (r["time"], r["source_order"], r["source_row"]))
        for seq, row in enumerate(rows, start=1):
            tick = {
                "time": row["time"],
                "ticker": row["ticker"],
                "market_state": _build_market_state(
                    {
                        "yes_ask": row["yes_ask"],
                        "no_ask": row["no_ask"],
                        "yes_bid": row["yes_bid"],
                        "no_bid": row["no_bid"],
                    }
                ),
                "seq": seq,
                "source_file": row["source_file"],
                "source_row": row["source_row"],
            }
            yield tick
        return []

    file_offsets: dict[Path, int] = {}
    file_headers: dict[Path, list[str]] = {}
    file_rows: dict[Path, int] = {}
    last_tick_ts: datetime | None = None
    last_heartbeat = time.time()
    seq = 0

    backfill_state: dict[Path, dict[str, object]] = {}

    def _init_file(path: Path, *, start_at_end: bool) -> None:
        with path.open("r", newline="") as handle:
            header_line = handle.readline()
            if not header_line:
                return
            file_headers[path] = [h.strip() for h in header_line.strip().split(",")]
            
            offset = 0
            if start_at_end:
                try:
                    # Re-open in binary to seek from end
                    with path.open("rb") as bh:
                        bh.seek(-8192, os.SEEK_END)
                        bh.readline() # Discard partial line
                        offset = bh.tell()
                except (OSError, ValueError):
                    offset = 0
            
            file_offsets[path] = offset
            file_rows[path] = 0
        file_size = 0
        try:
            file_size = path.stat().st_size
        except OSError:
            pass
        earliest_ts, latest_ts = _peek_file_time_bounds(path)
        mode = "tail" if start_at_end else "backfill"
        if ingest_log:
            ingest_log(
                {
                    "event": "FILE_DISCOVERED",
                    "wall_time": datetime.now().isoformat(),
                    "file": path.name,
                    "mode": mode,
                    "file_size": file_size,
                    "initial_offset": file_offsets.get(path, 0),
                    "earliest_ts": earliest_ts.isoformat() if earliest_ts else "",
                    "latest_ts": latest_ts.isoformat() if latest_ts else "",
                }
            )
            if start_at_end:
                ingest_log(
                    {
                        "event": "TAIL_START",
                        "wall_time": datetime.now().isoformat(),
                        "file": path.name,
                        "mode": mode,
                        "earliest_ts": earliest_ts.isoformat() if earliest_ts else "",
                        "latest_ts": latest_ts.isoformat() if latest_ts else "",
                    }
                )
            else:
                ingest_log(
                    {
                        "event": "BACKFILL_START",
                        "wall_time": datetime.now().isoformat(),
                        "file": path.name,
                        "mode": mode,
                        "earliest_ts": earliest_ts.isoformat() if earliest_ts else "",
                        "latest_ts": latest_ts.isoformat() if latest_ts else "",
                    }
                )
        if not start_at_end:
            backfill_state[path] = {"first_ts": None, "last_ts": None, "rows": 0, "done": False}

    initial_files = set(log_path.glob("market_data_*.csv"))

    while True:
        files = sorted(log_path.glob("market_data_*.csv"))
        for path in files:
            if path not in file_offsets:
                _init_file(path, start_at_end=(path in initial_files))
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
                        seq += 1
                        tick["seq"] = seq
                        tick["source_file"] = path.name
                        tick["source_row"] = file_rows.get(path, 0)
                        last_tick_ts = tick["time"]
                        state = backfill_state.get(path)
                        if state and not state.get("done"):
                            if state.get("first_ts") is None:
                                state["first_ts"] = tick["time"]
                            state["last_ts"] = tick["time"]
                            state["rows"] = int(state.get("rows") or 0) + 1
                        yield tick
                    file_rows[path] = file_rows.get(path, 0) + 1
                file_offsets[path] = handle.tell()
            state = backfill_state.get(path)
            if state and not state.get("done"):
                state["done"] = True
                if ingest_log:
                    ingest_log(
                        {
                            "event": "BACKFILL_COMPLETE",
                            "wall_time": datetime.now().isoformat(),
                            "file": path.name,
                            "mode": "backfill",
                            "backfill_first_ts": state.get("first_ts").isoformat()
                            if state.get("first_ts")
                            else "",
                            "backfill_last_ts": state.get("last_ts").isoformat()
                            if state.get("last_ts")
                            else "",
                            "backfill_rows": state.get("rows") or 0,
                        }
                    )
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
        seq = 0
        row_idx = 0
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
                    seq += 1
                    tick["seq"] = seq
                    tick["source_file"] = log_path.name
                    tick["source_row"] = row_idx
                    last_tick_ts = tick["time"]
                    yield tick
                row_idx += 1

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
                    seq += 1
                    tick["seq"] = seq
                    tick["source_file"] = log_path.name
                    tick["source_row"] = row_idx
                    last_tick_ts = tick["time"]
                    yield tick
                row_idx += 1
        return []

    df = pd.read_csv(path)
    if df.empty:
        return []
    if "tick_timestamp" in df.columns:
        ts_col = "ingest_timestamp" if use_ingest else "tick_timestamp"
    else:
        ts_col = "timestamp"
    df["_source_row"] = range(len(df))
    df = df.rename(columns={ts_col: "time"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time")
    for seq, row in enumerate(df.itertuples(index=False), start=1):
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
            "seq": seq,
            "source_file": os.path.basename(path),
            "source_row": row._source_row,
        }
        yield tick
