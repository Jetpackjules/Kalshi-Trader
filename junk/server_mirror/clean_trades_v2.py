import csv

input_file = 'trades_server.csv'
output_file = 'trades_cleaned.csv'

with open(input_file, 'r', newline='') as f:
    reader = csv.reader(f)
    header = next(reader)
    new_header = ["timestamp", "strategy", "ticker", "action", "price", "qty", "cost", "fee"]
    
    rows = []
    for row in reader:
        if not row: continue
        # Clean row: remove empty strings, spaces
        row = [cell.strip() for cell in row if cell.strip()]
        
        if len(row) < 2: continue # Skip empty/junk rows
        
        # If the first column is not a date-like string, skip
        if not row[0].startswith('202'): continue
        
        # If the second column is 'fee' or '0.00', it's a corrupted row
        if row[1] in ['fee', '0.00']: continue
        
        # Standardize to 8 columns
        if len(row) == 7:
            row.append("0.00")
        elif len(row) > 8:
            # Likely has extra fee or cost columns
            # We'll take the first 6 columns, then the last 2
            # But wait, let's see if we can identify cost and fee
            # In row 6: 2025-12-21 21:21:40.458889,Live RegimeSwitcher,KXHIGHNY-25DEC22-B36.5,BUY_YES,16,7,1.1900000000000002,0.07 ,0.00
            # row[6] = 1.19..., row[7] = 0.07, row[8] = 0.00
            # We'll take row[6] as cost and row[7] as fee (or row[8] if row[7] is junk)
            cost = row[6]
            fee = row[7]
            row = row[:6] + [cost, fee]
        elif len(row) < 8:
            while len(row) < 8:
                row.append("0.00")
        
        rows.append(row[:8])

with open(output_file, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(new_header)
    writer.writerows(rows)
print(f"Cleaned {len(rows)} rows.")
