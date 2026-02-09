
import pandas as pd
import glob
import os

DATA_DIR = "vm_logs/market_logs"
files = glob.glob(os.path.join(DATA_DIR, "market_data_*.csv"))
if files:
    df = pd.read_csv(files[0], nrows=1)
    print("Columns:", list(df.columns))
else:
    print("No files found.")
