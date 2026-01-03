import time
import json
import os
import glob
import re
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

# Configuration
LOG_DIR = "market_logs"
OBSERVER_STATUS_FILE = "observer_status.json"

class ObserverBot:
    def __init__(self):
        self.spread_histories = defaultdict(list)
        self.file_offsets = {}
        self.file_headers = {}
        
    def get_active_log_files(self):
        all_files = sorted(glob.glob(os.path.join(LOG_DIR, "market_data_*.csv")))
        active_files = []
        # Look for today's file or recent files
        today_str = datetime.now().strftime("%y%b%d").upper()
        for f in all_files:
            if today_str in f:
                active_files.append(f)
        return active_files

    def process_new_data(self, log_file):
        try:
            current_size = os.path.getsize(log_file)
            last_offset = self.file_offsets.get(log_file, 0)
            
            if current_size == last_offset:
                return
            
            with open(log_file, 'r') as f:
                if log_file not in self.file_headers:
                    header_line = f.readline().strip()
                    self.file_headers[log_file] = header_line.split(',')
                    f.seek(0, os.SEEK_END)
                    self.file_offsets[log_file] = f.tell()
                    return 
                
                f.seek(self.file_offsets[log_file])
                reader = csv.DictReader(f, fieldnames=self.file_headers[log_file])
                
                for row in reader:
                    self.on_tick(row)
                
                self.file_offsets[log_file] = f.tell()

        except Exception as e:
            pass

    def on_tick(self, row):
        ticker = row['market_ticker']
        try:
            # Parse prices
            ya = float(row.get('implied_yes_ask', 'nan'))
            yb = float(row.get('best_yes_bid', 'nan'))
            
            if pd.isna(ya) or pd.isna(yb): return
            
            spread = ya - yb
            mid = (ya + yb) / 2.0
            
            # Update History (ALWAYS)
            hist = self.spread_histories[ticker]
            hist.append(spread)
            if len(hist) > 500: hist.pop(0)
            
            # Calculate Threshold
            tight_threshold = np.percentile(hist, 50) if len(hist) > 100 else sum(hist)/len(hist) if len(hist) > 0 else 100
            is_tight = spread <= tight_threshold
            
            # Calculate Fair Price (MM Logic)
            # MM uses its own history of MIDs.
            # Let's approximate MM history using the same logic.
            # In LiveTrader, MM has `self.fair_prices` (list of mids).
            # It updates ONLY when called.
            # Here, we update ALWAYS.
            
            if not hasattr(self, 'mm_histories'):
                self.mm_histories = defaultdict(list)
            
            mm_hist = self.mm_histories[ticker]
            mm_hist.append(mid)
            if len(mm_hist) > 20: mm_hist.pop(0)
            
            fair_price = np.mean(mm_hist) if len(mm_hist) > 0 else mid
            
            # Write Status
            status = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "ticker": ticker,
                "mid": round(mid, 1),
                "spread": round(spread, 1),
                "fair_price": round(fair_price, 2),
                "is_tight": bool(is_tight),
                "threshold": round(tight_threshold, 2),
                "hist_len": len(hist)
            }
            
            # Write to JSON (Atomic write)
            temp_file = OBSERVER_STATUS_FILE + ".tmp"
            with open(temp_file, 'w') as f:
                json.dump(status, f)
            os.replace(temp_file, OBSERVER_STATUS_FILE)
            
        except Exception:
            pass

import csv

if __name__ == "__main__":
    bot = ObserverBot()
    print("Observer Bot Started...")
    while True:
        files = bot.get_active_log_files()
        for f in files:
            bot.process_new_data(f)
        time.sleep(0.1) # Fast poll
