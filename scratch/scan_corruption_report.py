import os, csv
from datetime import datetime

def scan_file(filepath, expected_prefixes=('201', '202')):
    """Return (first_corrupted_line, first_corrupted_date, total_corrupted).
    A row is considered corrupted if the timestamp column does NOT start with any of the expected prefixes.
    The function works on raw CSV without loading the whole file into memory.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        try:
            ts_idx = header.index('timestamp')
        except ValueError:
            # fallback: assume first column is timestamp
            ts_idx = 0
        first_corrupted_line = None
        first_corrupted_date = None
        total_corrupted = 0
        line_num = 1
        for row in reader:
            line_num += 1
            if not row or len(row) <= ts_idx:
                continue
            ts = row[ts_idx].strip()
            if not any(ts.startswith(p) for p in expected_prefixes):
                if first_corrupted_line is None:
                    first_corrupted_line = line_num
                    first_corrupted_date = ts
                total_corrupted += 1
        return first_corrupted_line, first_corrupted_date, total_corrupted


def main():
    data_dir = os.path.join(os.getcwd(), 'data')
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    print('=== Corruption Scan Report ===')
    for csv_file in sorted(csv_files):
        path = os.path.join(data_dir, csv_file)
        first_line, first_date, total = scan_file(path)
        if first_line:
            print(f"File: {csv_file}\n  First corrupted line: {first_line}\n  First corrupted timestamp: {first_date}\n  Total corrupted rows: {total}\n")
        else:
            print(f"File: {csv_file}\n  No corruption detected.\n")

if __name__ == '__main__':
    main()
