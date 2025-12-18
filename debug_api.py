import requests
import json
from datetime import datetime

# Try to get more data to see frequency
URL = "https://aviationweather.gov/api/data/metar?ids=KNYC&format=json&hours=12"

print(f"Fetching {URL}...")
try:
    response = requests.get(URL)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        try:
            data = response.json()
            print(f"Data type: {type(data)}")
            if isinstance(data, list):
                print(f"Number of records: {len(data)}")
                if len(data) > 0:
                    print("First 5 records timestamps:")
                    for item in data[:5]:
                        print(f"  {item.get('obsTime')} - Temp: {item.get('temp')}C")
                else:
                    print("Data list is empty.")
            else:
                print("Data is not a list.")
                print(str(data)[:200])
        except json.JSONDecodeError:
            print("Failed to decode JSON.")
            print("Raw text start:", response.text[:200])
    else:
        print("Request failed.")
        print("Raw text start:", response.text[:200])

except Exception as e:
    print(f"Exception: {e}")
