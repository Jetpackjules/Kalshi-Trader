import matplotlib.pyplot as plt
import pandas as pd

# Assuming asos_5min_df is available from the previous step and contains data for July 2025 KNYC

if not asos_5min_df.empty:
    print("Generating daily temperature plots for KNYC (July 2025) from NCEI 5-minute data...")

    # Ensure the timestamp column is datetime objects with timezone
    asos_5min_df['timestamp_lst'] = pd.to_datetime(asos_5min_df['timestamp_lst']).dt.tz_convert(new_york_tz)

    # Extract the date for grouping
    asos_5min_df['date'] = asos_5min_df['timestamp_lst'].dt.date

    # Get unique dates in July 2025 from the data
    # Filter for July 2025 specifically
    july_2025_dates = sorted(asos_5min_df[
        (asos_5min_df['timestamp_lst'].dt.year == 2025) &
        (asos_5min_df['timestamp_lst'].dt.month == 7)
    ]['date'].unique())


    if not july_2025_dates:
        print("No data found for July 2025 in the NCEI 5-minute DataFrame.")
    else:
        for single_date in july_2025_dates:
            # Filter data for the current date
            daily_df = asos_5min_df[asos_5min_df['date'] == single_date].copy()

            if not daily_df.empty:
                # Sort by timestamp for plotting
                daily_df = daily_df.sort_values(by='timestamp_lst')

                plt.figure(figsize=(12, 6))
                plt.plot(daily_df['timestamp_lst'], daily_df['temperature_f'], marker='o', linestyle='-', markersize=4)
                plt.title(f'Temperature for KNYC on {single_date.strftime("%Y-%m-%d")} (NCEI 5-min, America/New_York LST)')
                plt.xlabel('Time (America/New_York LST)')
                plt.ylabel('Temperature (°F)')
                plt.grid(True)
                plt.xticks(rotation=45)

                # Find the peak temperature and its timestamp for the current day
                peak_temp = daily_df['temperature_f'].max()
                peak_time = daily_df.loc[daily_df['temperature_f'].idxmax(), 'timestamp_lst']

                # Add a red dot at the peak temperature
                plt.plot(peak_time, peak_temp, 'ro', markersize=8)

                # Add a label with the peak temperature in big red letters
                plt.annotate(f'{peak_temp:.1f}°F',
                             (peak_time, peak_temp),
                             textcoords="offset points",
                             xytext=(0,10), # Offset the text above the point
                             ha='center',
                             fontsize=14,
                             color='red',
                             weight='bold')


                plt.tight_layout()
                plt.show()
            else:
                print(f"No data to plot for {single_date}.")

else:
    print("NCEI 5-minute DataFrame is empty. Cannot generate plots.")