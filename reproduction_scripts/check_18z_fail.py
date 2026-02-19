
import json
import ssl
from urllib.error import HTTPError
from urllib.parse import urlencode, quote
from urllib.request import urlopen
from datetime import datetime

# Configuration
MOS_API_URL = "https://mesonet.agron.iastate.edu/api/1/mos.json"
STATION = "KNYC"
MODEL = "NAM"
# The specific runtime that failed (Feb 15, 18:00 UTC)
RUNTIME = "2026-02-15 18:00" 

def check_18z_fail():
    print(f"--- Attempting to Fetch 18z Run for {RUNTIME} ---")
    
    params = {
        "station": STATION,
        "model": MODEL,
        "runtime": RUNTIME,
    }
    # Manually constructing URL to show exactly what is requested
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
                print("SUCCESS: Data found (Unexpected!)")
                print(f"Rows: {len(data['data'])}")
            else:
                print("SUCCESS-ish: Request succeeded but returned NO data (Empty List).")
                print(f"Response: {data}")
    except HTTPError as e:
        print(f"\nFAILURE CONFIRMED:")
        print(f"HTTP Error Code: {e.code}")
        print(f"Reason: {e.reason}")
        print("This verifies that the 18z run is missing/unavailable.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_18z_fail()
