
import json
from datetime import datetime
from urllib.request import urlopen
from urllib.parse import urlencode

MOS_API_URL = "https://mesonet.agron.iastate.edu/api/1/mos.json"

def check(station, model, runtime_str):
    params = {
        "station": station,
        "model": model,
        "runtime": runtime_str,
    }
    url = f"{MOS_API_URL}?{urlencode(params)}"
    print(f"Checking: {url}")
    try:
        with urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            rows = data.get("data", [])
            print(f"Result: {len(rows)} rows found.")
            if rows:
                print("First row:", rows[0])
            else:
                print("DATA EMPTY")
    except Exception as e:
        print(f"ERROR: {e}")

# Check a few combinations
check("KNYC", "NAM", "2026-02-09 12:00") # 12Z Yesterday (Should exist)
check("KJFK", "NAM", "2026-02-10 00:00") # 00Z Today (Alternative Station)
check("KNYC", "GFS", "2026-02-10 00:00") # 00Z Today (Alternative Model)
