


import requests, math
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo

UA = {"User-Agent": "nyc-temp-check (you@example.com)"}
TZ = zoneinfo.ZoneInfo("America/New_York")
STATIONS = ["KNYC","KLGA","KJFK","KEWR","KTEB"]  # include KNYC first (settlement station)

def climate_window_utc(d_local):
    # d_local is a date() in America/New_York for the climate day
    start_local = datetime(d_local.year, d_local.month, d_local.day, 0, 0, 0, tzinfo=TZ)
    # Climate day ends at midnight LST (01:00 local clock during DST)
    end_local = start_local + timedelta(days=1)
    if start_local.dst():
        end_local = start_local.replace(hour=1)
    return start_local.astimezone(zoneinfo.ZoneInfo("UTC")), end_local.astimezone(zoneinfo.ZoneInfo("UTC"))

def fetch_obs(station, start_utc, end_utc):
    url = f"https://api.weather.gov/stations/{station}/observations"
    params = {
        "start": start_utc.isoformat(timespec="seconds").replace("+00:00","Z"),
        "end":   end_utc.isoformat(timespec="seconds").replace("+00:00","Z"),
        "limit": 500
    }
    out = []
    while True:
        r = requests.get(url, params=params, headers=UA, timeout=20)
        r.raise_for_status()
        j = r.json()
        for f in j.get("features", []):
            p = f["properties"]
            c = p.get("temperature", {}).get("value")  # °C
            qc = str(p.get("temperature", {}).get("qualityControl", "V"))
            if c is None or qc not in ("V","C"):
                continue
            ts = datetime.fromisoformat(p["timestamp"].replace("Z","+00:00"))
            out.append({"ts_utc": ts, "temp_f": c*9/5+32})
        # pagination
        links = r.links or {}
        nxt = links.get("next", {}).get("url")
        if not nxt: break
        url, params = nxt, {}  # next already has query params
    return out

def peak_for_climate_day(station, d_local):
    s_utc, e_utc = climate_window_utc(d_local)
    obs = fetch_obs(station, s_utc, e_utc)
    if not obs:
        return None
    df = pd.DataFrame(obs)
    idx = df["temp_f"].idxmax()
    maxF = float(df.loc[idx, "temp_f"])
    tmax_local = df.loc[idx, "ts_utc"].astimezone(TZ)
    rounded = int(round(maxF))
    delta_to_next_up = (math.floor(maxF) + 0.5) - maxF
    return {
        "station": station,
        "date_climate_local": d_local.isoformat(),
        "maxF": round(maxF,1),
        "rounded": rounded,
        "tmax_local": tmax_local.isoformat(timespec="minutes"),
        "delta_to_next_up_degF": round(delta_to_next_up, 2)
    }

# Example: last 7 climate days, official feed, highest same-day granularity available
today_local = datetime.now(TZ).date()
rows = []
for i in range(7):
    d = today_local - timedelta(days=i)
    for st in STATIONS:
        rec = peak_for_climate_day(st, d)
        if rec: rows.append(rec)

df = pd.DataFrame(rows)
# wide comparison view by date
wide = df.pivot_table(index="date_climate_local", columns="station", values="maxF")
print(wide.sort_index(ascending=False))

