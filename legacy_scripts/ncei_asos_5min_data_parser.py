import pandas as pd
import os
from datetime import datetime
import pytz
import re # Import regular expressions

# Define the path to the downloaded file
download_dir = "asos_5min_data"
filename = "asos-5min-KNYC-202507.dat"
local_filepath = os.path.join(download_dir, filename)

# Define the New York timezone
new_york_tz = pytz.timezone('America/New_York')
utc_tz = pytz.timezone('UTC')

# Initialize a list to store extracted observations
extracted_observations = []

# Check if the file exists
if os.path.exists(local_filepath):
    print(f"Processing file: {local_filepath}")
    try:
        with open(local_filepath, 'r') as f:
            # Read the entire content of the file as a single string
            content = f.read().strip()

            # The first part might be a header or metadata
            # Based on the examples, each observation record seems to start with "94728KNYC"
            # We can use this as a delimiter to split the content into individual records.
            # Use re.split to split by "94728KNYC" and keep the delimiter in the result
            # The first element might be empty or header, so we process elements from index 1
            records = re.split(r'(94728KNYC)', content)

            # Filter out empty strings and combine the delimiter with the record content
            records = [records[i] + records[i+1] for i in range(1, len(records) - 1, 2)]
            # The last record might be incomplete if the file ends abruptly after the delimiter
            if len(records) % 2 == 1: # If odd number of elements after split, the last one is a full record
                 records.append(records.pop())


            print(f"Attempting to parse {len(records)} potential records based on '94728KNYC' delimiter...")

            # Analyze the provided data examples to determine fixed positions or patterns within each record
            # Example record structure inferred:
            # 94728KNYC NYC20250701000011907/01/25 00:00:31  5-MIN KNYC 010500Z AUTO 00000KT 9SM FEW019 SCT120 26/22 A2993 150 79 1500 000/00 RMK AO2 T02560217 $
            # StationID (e.g., KNYC), Date (e.g., 07/01/25), Time (e.g., 00:00:31), Temperature/Dewpoint (e.g., 26/22)
            # Date (MM/DD/YY) appears to start at index 20
            # Time (HH:MM:SS) appears to start at index 29
            # Temperature/Dewpoint (NN/NN) appears after ' AUTO '


            for record in records:
                try:
                    # Ensure the record starts with the expected delimiter
                    if not record.startswith('94728KNYC'):
                        # print(f"Skipping invalid record: {record[:50]}...") # Print a snippet
                        continue # Skip records that don't start with the delimiter

                    # Extract date string (MM/DD/YY) - appears to be at index 20
                    # Need to be careful with indexing if the record structure varies
                    # Let's try to find the date pattern (MM/DD/YY) after the initial part
                    date_match = re.search(r'(\d{2}/\d{2}/\d{2})', record[10:]) # Search after the initial part
                    date_str = date_match.group(1) if date_match else None

                    # Extract time string (HH:MM:SS) - appears after the date
                    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', record[date_match.end()+10:] if date_match else record) # Search after date
                    time_str = time_match.group(1) if time_match else None


                    # Find the position of ' AUTO ' to locate the temperature/dewpoint
                    auto_index = record.find(' AUTO ')
                    temp_dew_str = None

                    if auto_index != -1:
                        # Search for the temperature/dewpoint string after ' AUTO '
                        # It's the next non-whitespace sequence containing a '/'
                        remainder = record[auto_index + len(' AUTO '):].strip()
                        values_after_auto = remainder.split()
                        for val in values_after_auto:
                             if '/' in val and len(val.split('/')) == 2:
                                temp_dew_str = val
                                break # Found the temp/dewpoint string


                    if date_str and time_str and temp_dew_str:
                        # Combine date and time strings and parse
                        # Need to handle the year format (YY vs YYYY) - assuming 20YY
                        year_part = f"20{date_str.split('/')[-1]}"
                        month_day_part = '/'.join(date_str.split('/')[:2])
                        full_date_str = f"{month_day_part}/{year_part}"

                        # Combine date and time
                        datetime_str = f"{full_date_str} {time_str}"

                        # Parse the datetime string - format %m/%d/%Y %H:%M:%S
                        # Using errors='coerce' to turn unparseable dates into NaT
                        timestamp_utc = pd.to_datetime(datetime_str, format='%m/%d/%Y %H:%M:%S', errors='coerce').replace(tzinfo=utc_tz)

                        # Skip if timestamp parsing failed
                        if pd.isna(timestamp_utc):
                            # print(f"Skipping record due to timestamp parsing error: {record.strip()}")
                            continue

                        # Extract temperature (first part of temp/dewpoint string)
                        temperature_str = temp_dew_str.split('/')[0]
                        # Handle potential missing temperature value before '/'
                        if temperature_str:
                            temperature_c = float(temperature_str) # Assuming temperature is in Celsius
                        else:
                            # print(f"Skipping record due to missing temperature value: {record.strip()}")
                            continue # Skip if temperature value is missing


                        # Convert UTC timestamp to America/New_York LST
                        timestamp_lst = timestamp_utc.astimezone(new_york_tz)

                        # Convert temperature from Celsius to Fahrenheit
                        temperature_f = (temperature_c * 9/5) + 32

                        extracted_observations.append({
                            'station': 'KNYC', # Station is KNYC for this file
                            'timestamp_lst': timestamp_lst,
                            'temperature_f': temperature_f,
                            'source': 'NCEI_5min'
                        })
                    # else:
                        # print(f"Skipping record due to missing data components: {record.strip()}")

                except Exception as e:
                    # Handle other potential errors during processing a record
                    # print(f"Skipping record due to error: {record.strip()} - {e}")
                    pass # Skip records with errors


    except Exception as e:
        print(f"Error reading or processing the file {filename}: {e}")
else:
    print(f"File not found: {local_filepath}")


# Create a DataFrame from the extracted observations
if extracted_observations:
    asos_5min_df = pd.DataFrame(extracted_observations)
    print(f"\nSuccessfully extracted {len(asos_5min_df)} observations from {filename}")
    display(asos_5min_df.head())
else:
    print(f"\nNo observations extracted from {filename}.")