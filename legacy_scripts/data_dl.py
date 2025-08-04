import requests
import os

url = "https://www.ncei.noaa.gov/data/automated-surface-observing-system-five-minute/access/2025/07/asos-5min-KNYC-202507.dat"
download_dir = "asos_5min_data"
filename = url.split('/')[-1]
local_filepath = os.path.join(download_dir, filename)

os.makedirs(download_dir, exist_ok=True)

try:
    print(f"Attempting to download: {url}")
    response = requests.get(url, stream=True)
    response.raise_for_status()  # Raise an exception for bad status codes

    with open(local_filepath, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"Successfully downloaded: {filename}")

except requests.exceptions.RequestException as e:
    print(f"Failed to download {filename}: {e}")