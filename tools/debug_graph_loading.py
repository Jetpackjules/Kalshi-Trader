import csv
import json
from pathlib import Path
from datetime import datetime

def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    raw = value.replace("T", " ").replace("_", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H%M%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None

def load_variant(out_dir_str, label):
    out_dir = Path(out_dir_str)
    equity_history_path = out_dir / "equity_history.csv"
    
    print(f"Loading {label} from {equity_history_path}")
    
    if not equity_history_path.exists():
        print(f"File not found: {equity_history_path}")
        return

    daily_history_map = {}
    with open(equity_history_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = _parse_timestamp(row.get("date"))
            if not dt:
                continue
            
            date_key = dt.date().isoformat()
            daily_history_map[date_key] = float(row["equity"])
            
    sorted_keys = sorted(daily_history_map.keys())
    if sorted_keys:
        last_date = sorted_keys[-1]
        last_equity = daily_history_map[last_date]
        print(f"Final Equity for {label}: {last_equity} on {last_date}")
    else:
        print(f"No data found for {label}")

def main():
    variants = [
        ("unified_engine_comparison_dec05\\grid_r80_n20_m6_t10_s2", "grid_r80_n20_m6_t10_s2"),
        ("unified_engine_comparison_dec05\\grid_r100_n20_m8_t10_s2", "grid_r100_n20_m8_t10_s2")
    ]
    
    for out_dir, label in variants:
        load_variant(out_dir, label)

if __name__ == "__main__":
    main()
