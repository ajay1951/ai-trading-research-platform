import os, glob, pandas as pd

DATA_DIR = os.path.join(os.getcwd(), 'data')
OUTPUT_SUFFIX = '_clean'

# To capture a snippet for demonstration
def capture_snippet(df, idx, window=3):
    start = max(idx - window, 0)
    end = min(idx + window + 1, len(df))
    return df.iloc[start:end]

# Containers for reporting
report = []

for csv_path in sorted(glob.glob(os.path.join(DATA_DIR, '*.csv')):
    filename = os.path.basename(csv_path)
    df = pd.read_csv(csv_path)
    # Identify timestamp column (common name)
    if 'timestamp' in df.columns:
        ts_col = 'timestamp'
    else:
        ts_col = df.columns[0]
    # Try to parse dates, coercing errors to NaT
    parsed = pd.to_datetime(df[ts_col], errors='coerce', utc=True)
    # Detect first corrupted index (first NaT after a valid series)
    corrupted_idx = None
    if parsed.isna().any():
        # Find first NaT
        corrupted_idx = parsed[parsed.isna()].index[0]
    # Determine start date from first valid entry
    first_valid = parsed.dropna().iloc[0]
    total_rows = len(df)
    # Infer frequency from the first 20 valid diffs (most common)
    diffs = parsed.dropna().diff().dropna()
    # Use the mode of diffs (as Timedelta) for frequency
    if not diffs.empty:
        freq = diffs.mode()[0]
    else:
        # fallback to daily
        freq = pd.Timedelta(days=1)
    # Generate clean timestamp range
    clean_range = pd.date_range(start=first_valid, periods=total_rows, freq=freq)
    # Replace column with formatted strings matching original style
    # Detect if original had time component (len of string > 10)
    sample_val = df[ts_col].iloc[0]
    has_time = len(str(sample_val)) > 10
    fmt = '%Y-%m-%d %H:%M:%S' if has_time else '%Y-%m-%d'
    df[ts_col] = clean_range.strftime(fmt)

    # Save cleaned file
    clean_path = os.path.splitext(csv_path)[0] + OUTPUT_SUFFIX + '.csv'
    df.to_csv(clean_path, index=False)

    # Capture snippet around corruption for report (if any)
    if corrupted_idx is not None:
        before = capture_snippet(df, corrupted_idx)
        # Load original raw for before‑fix snippet
        orig_df = pd.read_csv(csv_path)
        orig_before = capture_snippet(orig_df, corrupted_idx)
        report.append({
            'file': filename,
            'corrupted_line': int(corrupted_idx) + 1,  # +1 for header offset
            'original_snippet': orig_before.to_dict(orient='list'),
            'fixed_snippet': before.to_dict(orient='list')
        })
    else:
        report.append({
            'file': filename,
            'corrupted_line': None,
            'original_snippet': None,
            'fixed_snippet': None
        })

# Write a brief JSON‑like report for the user
report_path = os.path.join(os.getcwd(), 'scratch', 'timestamp_fix_report.txt')
with open(report_path, 'w', encoding='utf-8') as f:
    for entry in report:
        f.write(f"File: {entry['file']}\n")
        if entry['corrupted_line']:
            f.write(f"  First corrupted line: {entry['corrupted_line']}\n")
            f.write("  Original snippet (around corruption):\n")
            for col, vals in entry['original_snippet'].items():
                f.write(f"    {col}: {vals}\n")
            f.write("  Fixed snippet (same rows after fixing):\n")
            for col, vals in entry['fixed_snippet'].items():
                f.write(f"    {col}: {vals}\n")
        else:
            f.write("  No corruption detected.\n")
        f.write("\n")
print('✅ Timestamp repair completed for all CSVs.')
print('Report written to', report_path)
