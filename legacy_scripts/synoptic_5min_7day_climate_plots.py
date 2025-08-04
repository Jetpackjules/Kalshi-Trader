# === Plot past 7 climate days at highest available granularity (Synoptic 5-min) ===
# Uses your robust Synoptic parser and adds: per-day plots + an overlay plot + peak summary

import requests, math, re
import pandas as pd
from datetime import datetime, timedelta, date
import zoneinfo
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---- HARDCODED CREDS ----
SYNOPTIC_TOKEN = "ee1f7ca7e6ae46aca3bc8693e1205e03"   # data requests use this
SYNOPTIC_API_KEY = "PUT_YOUR_PRIVATE_KEY_HERE"         # not used below

TZ   = zoneinfo.ZoneInfo("America/New_York")
TARGET_STATION = "KNYC"   # change to KLGA/KJFK/KEWR/KTEB if desired
BASE = "https://api.synopticdata.com/v2/stations/timeseries"

def climate_window_local(d_local: date):
    """NYC climate day: 00:00 LST → next 00:00 LST (01:00 local during DST)."""
    start = datetime(d_local.year, d_local.month, d_local.day, 0, 0, tzinfo=TZ)
    end   = start + timedelta(days=1)
    if start.dst():  # summer: climate day ends 01:00 local
        end += timedelta(hours=1)
    return start, end

def _fmt_local(dt: datetime) -> str:
    # Synoptic expects YYYYmmddHHMM (no 'T') for start/end
    return dt.strftime("%Y%m%d%H%M")

def _parse_synoptic_time(s: str) -> datetime:
    """Parse '...Z', '...-0400', or '...-04:00' into tz-aware NYC time."""
    s = s.replace(" ", "T")
    if s.endswith("Z"):
        dt = datetime.fromisoformat(s.replace("Z","+00:00"))
    elif re.search(r"[+-]\d{4}$", s):     # 2025-07-25T20:00:00-0400
        s = s[:-2] + ":" + s[-2:]
        dt = datetime.fromisoformat(s)
    else:                                  # 2025-07-25T20:00:00-04:00 or already with offset
        dt = datetime.fromisoformat(s)
    return dt.astimezone(TZ)

def fetch_synoptic_series(stid: str, start_local: datetime, end_local: datetime):
    """Return list of {ts_local, temp_f} at ~5-min cadence for [start,end) local."""
    params = {
        "stid": stid,
        "vars": "air_temp",
        "start": _fmt_local(start_local),
        "end":   _fmt_local(end_local),
        "units": "temp|F",
        "obtimezone": "local",
        "token": SYNOPTIC_TOKEN
    }
    r = requests.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    if not j.get("STATION"):
        return []
    S = j["STATION"][0].get("OBSERVATIONS", {})

    # ---- Handle both possible shapes ----
    vals = None
    vobj = S.get("air_temp_value_1")
    if isinstance(vobj, dict) and isinstance(vobj.get("value"), list):
        vals = vobj["value"]
    if vals is None and isinstance(S.get("air_temp_set_1"), list):
        vals = S["air_temp_set_1"]

    # Times: prefer local; fall back to date_time or utc
    times = S.get("date_time_local") or S.get("date_time") or S.get("date_time_utc") or []
    if not vals or not times:
        return []

    out = []
    for t, v in zip(times, vals):
        if v is None:
            continue
        try:
            ts_local = _parse_synoptic_time(t)
        except Exception:
            continue
        v = float(v)
        if -80 < v < 130:  # sanity bounds
            out.append({"ts_local": ts_local, "temp_f": v})
    return out

def fetch_day_df(station: str, d_local: date) -> pd.DataFrame:
    s_local, e_local = climate_window_local(d_local)
    obs = fetch_synoptic_series(station, s_local, e_local)
    if not obs:
        return pd.DataFrame(columns=["ts_local","temp_f","date"])
    df = pd.DataFrame(obs)
    df["date"] = pd.to_datetime(d_local)
    return df.sort_values("ts_local")

# ---- build 7 days of data (today back to day-6) ----
today_local = datetime.now(TZ).date()
days = [today_local - timedelta(days=i) for i in range(7)]
days.sort()  # oldest -> newest

series_per_day = []
for d in days:
    df_day = fetch_day_df(TARGET_STATION, d)
    if df_day.empty:
        print(f"[WARN] {TARGET_STATION} {d}: no Synoptic temps in climate window.")
    series_per_day.append(df_day)

# ---- per-day individual plots ----
for df_day, d in zip(series_per_day, days):
    if df_day.empty:
        continue
    # annotate peak
    i = df_day["temp_f"].idxmax()
    tmax = df_day.loc[i, "ts_local"]
    vmax = df_day.loc[i, "temp_f"]

    plt.figure(figsize=(9,4))
    plt.plot(df_day["ts_local"], df_day["temp_f"])
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=TZ))
    plt.title(f"{TARGET_STATION} temperature – {d.isoformat()} (climate day)")
    plt.xlabel("Local time")
    plt.ylabel("Temp (°F)")
    plt.grid(True, alpha=0.3)
    plt.scatter([tmax],[vmax])
    plt.annotate(f"{vmax:.1f}°F @ {tmax.strftime('%H:%M')}",
                 xy=(tmax, vmax), xytext=(10,10), textcoords="offset points")
    plt.tight_layout()
    plt.show()

# ---- overlay plot: all 7 days on one time-of-day axis ----
# Convert to "time since local midnight" for each climate day
def to_tod_minutes(ts: pd.Series) -> pd.Series:
    return ts.dt.hour*60 + ts.dt.minute + ts.dt.second/60.0

plt.figure(figsize=(10,5))
labels = []
for df_day, d in zip(series_per_day, days):
    if df_day.empty:
        continue # Skip plotting if the dataframe is empty
    tod_min = to_tod_minutes(df_day["ts_local"])
    plt.plot(tod_min, df_day["temp_f"])
    labels.append(d.isoformat()) # Use date as label


plt.xticks([0,180,360,540,720,900,1080,1260], ["00:00","03:00","06:00","09:00","12:00","15:00","18:00","21:00"])
plt.title(f"{TARGET_STATION} – last 7 climate days (overlay)")
plt.xlabel("Local time of day")
plt.ylabel("Temp (°F)")
plt.grid(True, alpha=0.3)
plt.legend(labels, title="Date", ncol=2, fontsize=8)
plt.tight_layout()
plt.show()

# ---- quick peak summary table ----
rows = []
for df_day, d in zip(series_per_day, days):
    if df_day.empty:
        rows.append({"date": d.isoformat(), "peak_F": None, "time_local": None, "samples": 0})
    else:
        i = df_day["temp_f"].idxmax()
        rows.append({
            "date": d.isoformat(),
            "peak_F": round(float(df_day.loc[i,"temp_f"]),1),
            "time_local": df_day.loc[i,"ts_local"].strftime("%Y-%m-%d %H:%M"),
            "samples": int(len(df_day))
        })
peak_summary = pd.DataFrame(rows)
print("\nPeak summary (last 7 climate days):")
print(peak_summary)