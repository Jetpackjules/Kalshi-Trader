
import pandas as pd
import re
import datetime

log_path = "server_mirror/output.log"

def main():
    print(f"--- Analyzing Latency in {log_path} ---")
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("Log not found.")
        return

    latencies = []
    
    # [DIAG] event=TICK_IN log_ts=... tick_ts=...
    # [DIAG] event=DECISION log_ts=... tick_ts=...
    
    for line in lines:
        if "event=DECISION" in line:
            # Extract timestamps
            m_log = re.search(r'log_ts=([\d\.-]+T[\d:.-]+)', line)
            m_tick = re.search(r'tick_ts=([\d\.-]+T[\d:.-]+)', line)
            
            if m_log and m_tick:
                try:
                    ts_log = pd.to_datetime(m_log.group(1))
                    ts_tick = pd.to_datetime(m_tick.group(1))
                    
                    diff = (ts_log - ts_tick).total_seconds()
                    # Filter out insane outliers (clocks might be drifted if not synced, but diff should be small)
                    if 0 <= diff < 60:
                        latencies.append(diff)
                except:
                    pass

    if latencies:
        s = pd.Series(latencies)
        print(f"Count: {len(s)}")
        print(f"Mean Latency:   {s.mean()*1000:.1f} ms")
        print(f"Median Latency: {s.median()*1000:.1f} ms")
        print(f"90th %ile:      {s.quantile(0.90)*1000:.1f} ms")
        print(f"99th %ile:      {s.quantile(0.99)*1000:.1f} ms")
        print(f"Max Latency:    {s.max()*1000:.1f} ms")
    else:
        print("No decision logs found.")

if __name__ == "__main__":
    main()
