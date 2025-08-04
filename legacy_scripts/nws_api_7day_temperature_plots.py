import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import pytz
import matplotlib.pyplot as plt

# Define the station and timezone
station = 'KNYC'
new_york_tz = pytz.timezone('America/New_York')
utc_tz = pytz.timezone('UTC')

# Get today's date in UTC
utc_now = datetime.utcnow()

# Store the downloaded data for the past 7 days
nws_data_7_days = {}

print(f"Fetching data for the past 7 days from NWS API for station {station}...")

for i in range(7):
    current_day_utc = utc_now - timedelta(days=i)
    start_of_day_utc = current_day_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day_utc = start_of_day_utc + timedelta(days=1) - timedelta(microseconds=1)

    print(f"\n  Fetching data for {current_day_utc.date()} (UTC)")

    start_time_utc_iso = start_of_day_utc.isoformat(timespec='seconds') + 'Z'
    end_time_utc_iso = end_of_day_utc.isoformat(timespec='seconds') + 'Z'

    api_url = f"https://api.weather.gov/stations/{station}/observations"
    params = {
        'start': start_time_utc_iso,
        'end': end_time_utc_iso,
        'limit': 499 # Changed limit to 499
    }

    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()

        observations = []
        if 'features' in data:
            for feature in data['features']:
                if 'properties' in feature:
                    properties = feature['properties']
                    timestamp = properties.get('timestamp')
                    temperature_c = properties.get('temperature', {}).get('value')

                    if timestamp and temperature_c is not None:
                        # Convert timestamp to datetime object and localize to UTC, then convert to NY LST
                        timestamp_utc = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).replace(tzinfo=utc_tz)
                        timestamp_lst = timestamp_utc.astimezone(new_york_tz)

                        temperature_f = (temperature_c * 9/5) + 32
                        observations.append({
                            'timestamp_lst': timestamp_lst,
                            'temperature_f': temperature_f,
                            'date': timestamp_lst.date() # Extract date for plotting
                        })
        if observations:
            nws_data_7_days[current_day_utc.date()] = pd.DataFrame(observations)
            print(f"    Successfully fetched {len(observations)} observations.")
        else:
            print("    No observations found.")

    except requests.exceptions.RequestException as e:
        print(f"    Failed to fetch data: {e}")


# Plot temperature for each day
if nws_data_7_days:
    print("\nGenerating plots for each day...")
    for date, df in nws_data_7_days.items():
        if not df.empty:
            df = df.sort_values(by='timestamp_lst') # Sort by timestamp for plotting

            plt.figure(figsize=(10, 6))
            plt.plot(df['timestamp_lst'], df['temperature_f'], marker='o', linestyle='-')
            plt.title(f'Temperature for {station} on {date.strftime("%Y-%m-%d")} (America/New_York LST)')
            plt.xlabel('Time (America/New_York LST)')
            plt.ylabel('Temperature (°F)')
            plt.grid(True)
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.show()
        else:
            print(f"No data to plot for {date}.")
else:
    print("\nNo NWS data was successfully downloaded for the past 7 days.")