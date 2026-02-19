
import json
import ssl
from datetime import datetime, UTC
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

MOS_API_URL = "https://mesonet.agron.iastate.edu/api/1/mos.json"

def http_get_json(url: str, params: dict) -> dict:
    full_url = f"{url}?{urlencode(params)}"
    print(f"Fetching: {full_url}")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urlopen(full_url, timeout=20, context=ctx) as response:
        return json.load(response)

def inspect_run(date_str: str, target_date_str: str):
    params = {
        "station": "KNYC",
        "model": "NAM",
        "runtime": date_str,
    }
    try:
        data = http_get_json(MOS_API_URL, params)
        if not data or not data.get("data"):
            print("No data found.")
            return

        print(f"--- Data for Runtime {date_str} ---")
        rows = data['data']
        
        target_rows = []
        for row in rows:
            # ftime looks like "2026-02-16 00:00:00 UTC" or similar iso
            # The API returns 'ftime' as timestamp string.
            # We want rows where the local date (ET) is the target date.
            # Simply printing all rows to see values.
            
            # Simple filter for display
            if target_date_str in row['ftime']:
                print(f"Time: {row['ftime']} | Temp: {row['tmp']} | Dew: {row['dpt']}")
                try:
                    target_rows.append(float(row['tmp']))
                except:
                    pass
        
        if target_rows:
            print(f"Max Temp for {target_date_str}: {max(target_rows)}")
        else:
            print(f"No rows found matching {target_date_str}")

    except HTTPError as e:
        print(f"HTTP Error: {e}")

if __name__ == "__main__":
    # Check Feb 15 12:00 UTC run for data on Feb 16
    inspect_run("2026-02-15 12:00", "2026-02-16")
