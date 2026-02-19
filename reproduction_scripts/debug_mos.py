
import json
import ssl
from datetime import datetime, UTC
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen, Request

MOS_API_URL = "https://mesonet.agron.iastate.edu/api/1/mos.json"

def http_get_json(url: str, params: dict) -> dict:
    full_url = f"{url}?{urlencode(params)}"
    print(f"Fetching: {full_url}")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(full_url, timeout=20, context=ctx) as response:
            return json.load(response)
    except HTTPError as exc:
        print(f"HTTP Error: {exc.code} {exc.reason}")
        raise
    except Exception as exc:
        print(f"Error: {exc}")
        raise

def check_run(date_str: str, model: str = "NAM", station: str = "KNYC"):
    # date_str format: YYYY-MM-DD HH:MM (UTC)
    params = {
        "station": station,
        "model": model,
        "runtime": date_str,
    }
    try:
        data = http_get_json(MOS_API_URL, params)
        if data and data.get("data"):
            print(f"SUCCESS: Found {len(data['data'])} rows for {date_str}")
            # print sample
            print(f"Sample: {data['data'][0]}")
        else:
            print(f"FAILURE: No data in response/rows for {date_str}")
    except HTTPError as e:
        if e.code == 404:
            print(f"FAILURE: 404 Not Found for {date_str}")

if __name__ == "__main__":
    # Check Feb 15 18:00 UTC (The target run)
    print("--- Checking NAM 18z ---")
    check_run("2026-02-15 18:00")
    
    print("\n--- Checking NAM 12z (Fallback) ---")
    check_run("2026-02-15 12:00")

    print("\n--- Checking GFS 18z (Comparison) ---")
    check_run("2026-02-15 18:00", model="GFS")
