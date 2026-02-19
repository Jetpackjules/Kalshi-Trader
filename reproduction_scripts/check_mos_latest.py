
import json
import ssl
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

MOS_API_URL = "https://mesonet.agron.iastate.edu/api/1/mos.json"

def test_no_runtime():
    print("--- Testing MOS API without 'runtime' parameter ---")
    params = {
        "station": "KNYC",
        "model": "NAM",
        # "runtime": OMITTED
    }
    full_url = f"{MOS_API_URL}?{urlencode(params)}"
    print(f"Fetching: {full_url}")
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        with urlopen(full_url, timeout=20, context=ctx) as response:
            data = json.load(response)
            if data:
                print("SUCCESS? Received data.")
                print(f"Keys: {data.keys()}")
                if 'data' in data and len(data['data']) > 0:
                    print(f"Sample Row: {data['data'][0]}")
                # Check what runtime it returned
                if 'data' in data and len(data['data']) > 0:
                    print(f"Returned Runtime: {data['data'][0].get('runtime')}")
            else:
                print("Response Empty")
    except HTTPError as e:
        print(f"HTTP Error: {e.code} {e.reason}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_no_runtime()
