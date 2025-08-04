# Past ~30 days of NYC (Central Park) CLI → CSV: date,tmax,tmax_time,tmin,tmin_time
import re, requests
from datetime import datetime

ISSUEDBY = "NYC"  # change to e.g. "BOS", "DCA", "LAX" for other cities
UA = {"User-Agent": "kalshi-wsl (you@example.com)"}  # use a real contact if you can

def parse_time(tok: str) -> str:
    if not tok: return ""
    m = re.fullmatch(r"\s*(\d{1,4})\s*([AP]M)\s*", tok.upper())
    if not m: return ""
    n, ampm = m.groups()
    n = n.zfill(4)        # 207 -> 0207, 57 -> 0057
    hh, mm = int(n[:2]), int(n[2:])
    if ampm == "AM": hh = 0 if hh == 12 else hh
    else:            hh = 12 if hh == 12 else hh + 12
    return f"{hh:02d}:{mm:02d}"

def extract(text: str):
    # Date line like: "...SUMMARY FOR AUGUST 2 2025..."
    dm = re.search(r"SUMMARY FOR ([A-Z]+ \d{1,2} \d{4})", text)
    d_cli = dm.group(1).title() if dm else ""
    d_iso = ""
    try: d_iso = datetime.strptime(d_cli, "%B %d %Y").date().isoformat()
    except: pass

    # MAX/MIN with optional times
    mmax = re.search(r"(?m)^\s*MAXIMUM(?: TEMPERATURE \(F\))?\s+(\d{1,3})(?:\s+(\d{1,4}\s+[AP]M))?", text)
    mmin = re.search(r"(?m)^\s*MINIMUM(?: TEMPERATURE \(F\))?\s+(\d{1,3})(?:\s+(\d{1,4}\s+[AP]M))?", text)
    tmax  = int(mmax.group(1)) if mmax else None
    tmin  = int(mmin.group(1)) if mmin else None
    tmax_t = parse_time(mmax.group(2)) if (mmax and mmax.group(2)) else ""
    tmin_t = parse_time(mmin.group(2)) if (mmin and mmin.group(2)) else ""
    return (d_iso or d_cli), tmax, tmax_t, tmin, tmin_t

def fetch_cli(version: int) -> str:
    url = (f"https://forecast.weather.gov/product.php?"
           f"site=NWS&issuedby={ISSUEDBY}&product=CLI&format=TXT&version={version}&glossary=0")
    r = requests.get(url, headers=UA, timeout=10)
    r.raise_for_status()
    return r.text

rows, seen = [], set()
for v in range(0, 120):  # crawl back ~120 products to get ~30 unique days
    print("trying: ", v)
    try:
        text = fetch_cli(v)
        d, tmax, tmax_t, tmin, tmin_t = extract(text)
        if not d or d in seen: 
            continue
        seen.add(d)
        rows.append((d, tmax, tmax_t, tmin, tmin_t))
        if len(rows) >= 31:
            break
    except requests.HTTPError:
        continue  # skip holes

# Sort chronologically if possible
try: rows.sort(key=lambda x: datetime.fromisoformat(x[0]))
except: pass

print("date,tmax_f,tmax_time_local,tmin_f,tmin_time_local")
for d, tmax, tx, tmin, tn in rows:
    print(f"{d},{'' if tmax is None else tmax},{tx},{'' if tmin is None else tmin},{tn}")
