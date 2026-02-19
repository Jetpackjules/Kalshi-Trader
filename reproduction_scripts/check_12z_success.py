
import json
import ssl
from urllib.error import HTTPError
from urllib.parse import urlencode, quote
from urllib.request import urlopen
from datetime import datetime

# Configuration
MOS_API_URL = "https://mesonet.agron.iastate.edu/api/1/mos.json"

def check_12z_success():
    # 2pm PST = 5pm EST = 22:00 UTC
    # Since 18z (1pm EST) failed, the bot fell back to 12z (7am EST).
    # This is the command that returned the 39.0 F forecast.
    
    RUNTIME = "2026-02-15 12:00" # 12z Run
    
    print(f"--- Attempting to Fetch 12z Run (Fallback) for {RUNTIME} ---")
    
    params = {
        "station": "KNYC",
        "model": "NAM",
        "runtime": RUNTIME,
    }
    
    full_url = f"{MOS_API_URL}?{urlencode(params, quote_via=quote)}"
    print(f"URL: {full_url}")
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    print("\nSending Request...")
    try:
        with urlopen(full_url, timeout=10, context=ctx) as response:
            data = json.load(response)
            if data and data.get('data'):
                print("SUCCESS: Data Found (12z Run)")
                rows = data['data']
                print(f"Total Rows: {len(rows)}")
                
                # Filter for Feb 16 Target
                target_date = "2026-02-16"
                max_tmp = None
                
                print(f"\n--- Scanning for Max Temp on {target_date} ---")
                found_any = False
                for row in rows:
                    ftime = row['ftime'][:10] # 'YYYY-MM-DD'
                    if ftime == target_date:
                        found_any = True
                        tmp = row.get('tmp')
                        if tmp is not None:
                            print(f"Time: {row['ftime'][11:16]} | Temp: {tmp} F")
                            if max_tmp is None or tmp > max_tmp:
                                max_tmp = tmp
                
                if found_any:
                    print(f"\nFINAL FORECAST (MAX): {max_tmp} F")
                else:
                    print("No data found for target date.")
                    
            else:
                print("Request succeeded but returned NO data.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_12z_success()
