
import os
import time
import csv
from pathlib import Path
from server_mirror.unified_engine.tick_sources import iter_ticks_from_market_logs

def test_safe_warmup_large():
    # Create a dummy market log
    log_dir = "debug_warmup_large"
    os.makedirs(log_dir, exist_ok=True)
    log_file = Path(log_dir) / "market_data_TEST_LARGE.csv"
    
    # Write 1000 lines (approx 80KB)
    with open(log_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp","market_ticker","best_yes_bid","best_no_bid","implied_no_ask","implied_yes_ask","last_trade_price"])
        for i in range(1000):
            writer.writerow([f"2026-01-12T08:00:{i%60:02d}.{i:06d}", "TEST-TICKER", 10, 90, 91, 11, 0])

    print("Created dummy log with 1000 lines.")

    # Run iter_ticks with follow=True
    # It should read the last ~8192 bytes.
    # Each line is ~70 bytes.
    # 8192 / 70 ~= 117 lines.
    # So we expect to see seq numbers starting around 880.
    
    print("Starting tick iterator...")
    iterator = iter_ticks_from_market_logs(log_dir, follow=True, poll_s=0.1)
    
    count = 0
    first_seq = None
    start_time = time.time()
    for tick in iterator:
        if first_seq is None:
            first_seq = tick['seq']
            print(f"First tick read: Seq={tick['seq']} Time={tick['time']}")
        
        count += 1
        if count >= 200: # Read enough to verify start point
            break
        if time.time() - start_time > 5:
            break
            
    print(f"Total ticks read: {count}")
    
    if count > 0 and first_seq > 1:
        print(f"SUCCESS: Started at seq {first_seq} (Tail read worked).")
    elif first_seq == 1:
        print("FAILURE: Started at seq 1 (Read WHOLE file - seek failed?).")
    else:
        print("FAILURE: Read 0 lines.")

if __name__ == "__main__":
    test_safe_warmup_large()
