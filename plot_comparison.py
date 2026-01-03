import pandas as pd
import matplotlib.pyplot as plt
import re
from datetime import datetime



def parse_real_equity(filename):
    data = []
    # Try UTF-16 first (PowerShell default), then default
    try:
        with open(filename, 'r', encoding='utf-16') as f:
            content = f.read()
    except:
        with open(filename, 'r', errors='ignore') as f:
            content = f.read()
            
    if "=== REAL PORTFOLIO EQUITY CSV ===" in content:
        section = content.split("=== REAL PORTFOLIO EQUITY CSV ===")[1]
        lines = section.strip().split('\n')
        for line in lines:
            if ',' in line and 'Date' not in line:
                parts = line.split(',')
                date_str = parts[0].strip()
                try:
                    equity = float(parts[1].strip())
                    data.append({'Date': pd.to_datetime(date_str), 'RealEquity': equity})
                except: pass
    return pd.DataFrame(data)

def parse_sim_equity(filename):
    data = []
    with open(filename, 'r', encoding='utf-16', errors='ignore') as f:
        content = f.read()
        lines = content.split('\n')
        for line in lines:
            if "[Day End" in line and "Equity:" in line:
                try:
                    # Example: [Day End 25DEC23] Buggy (Live) Equity: $10000.00 (Cash $10000.00)
                    date_part = line.split('[Day End ')[1].split(']')[0] # 25DEC23
                    # Split by 'Equity: $' then take first token
                    equity_part = line.split('Equity: $')[1].split()[0] 
                    
                    # Example: [Day End 25DEC23] -> Year 25, Month DEC, Day 23
                    dt = datetime.strptime(date_part, "%y%b%d")
                    # dt = dt.replace(year=2025) # Not needed if %y is 25
                    
                    # print(f"Found Sim: {dt} {equity_part}")
                    data.append({'Date': dt, 'SimEquity': float(equity_part)})
                except Exception as e:
                    print(f"Error parsing line: {line} - {e}")
    
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.drop_duplicates(subset='Date', keep='last')
    return df

def main():
    sim_df = parse_sim_equity('sim_output_realistic.txt')
    real_df = parse_real_equity('real_equity_dump.txt')
    
    print("--- SIM DATA ---")
    print(sim_df)
    print("\n--- REAL DATA ---")
    print(real_df)
    
    if sim_df.empty:
        print("Sim data empty. Simulation might still be running or failed.")
        return
    if real_df.empty:
        print("Real data empty.")
        return

    # Merge
    merged = pd.merge(sim_df, real_df, on='Date', how='outer').sort_values('Date')
    
    # Normalize to start at 100% (Indexed to first common date)
    # Find first date where both exist
    common = merged.dropna()
    if common.empty:
        print("No overlapping dates.")
        # Just plot raw
    else:
        start_date = common['Date'].min()
        base_sim = common[common['Date'] == start_date]['SimEquity'].values[0]
        base_real = common[common['Date'] == start_date]['RealEquity'].values[0]
        
        merged['SimROI'] = (merged['SimEquity'] / base_sim - 1) * 100
        merged['RealROI'] = (merged['RealEquity'] / base_real - 1) * 100

    print(merged)
    
    # Plot
    plt.figure(figsize=(10, 6))
    if 'SimROI' in merged.columns:
        plt.plot(merged['Date'], merged['SimROI'], label='Simulated ROI (Realistic Capital)', marker='o')
        plt.plot(merged['Date'], merged['RealROI'], label='Real Portfolio ROI', marker='x')
        plt.ylabel('ROI (%)')
    else:
        plt.plot(merged['Date'], merged['SimEquity'], label='Simulated Equity', marker='o')
        plt.plot(merged['Date'], merged['RealEquity'], label='Real Equity', marker='x')
        plt.ylabel('Equity ($)')
        
    plt.title('Backtester vs Live Bot Performance (Realistic Capital)')
    plt.xlabel('Date')
    plt.legend()
    plt.grid(True)
    plt.savefig('comparison_chart.png')
    print("Chart saved to comparison_chart.png")

if __name__ == "__main__":
    main()
