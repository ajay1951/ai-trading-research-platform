import os, glob, pandas as pd

DATA_DIR = os.path.join(os.getcwd(), 'data')
OUTPUT_SUFFIX = '_clean'

def capture_snippet(df, idx, window=3):
    start = max(idx - window, 0)
    end = min(idx + window + 1, len(df))
    return df.iloc[start:end]

report = []

for csv_path in sorted(glob.glob(os.path.join(DATA_DIR, '*.csv'))):
    filename = os.path.basename(csv_path)
    df = pd.read_csv(csv_path)
    # Determine timestamp column name (most common is 'timestamp')
    ts_col = 'timestamp' if 'timestamp' in df.columns else df.columns[0]
    # Parse timestamps, coercing errors to NaT
    parsed = pd.to_datetime(df[ts_col], errors='coerce', utc=True)
    # Find first NaT (corrupted) index, if any
    corrupted_idx = None
    if parsed.isna().any():
        corrupted_idx = parsed[parsed.isna()].index[0]
    # First valid timestamp (skip any leading NaT)
    first_valid = parsed.dropna().iloc[0]
    total_rows = len(df)
    # Infer frequency from the most common difference among the first 100 valid rows
    diffs = parsed.dropna().diff().dropna()
    if not diffs.empty:
        freq = diffs.mode()[0]
    else:
        freq = pd.Timedelta(days=1)
    # Build a clean date_range matching the original length
    clean_range = pd.date_range(start=first_valid, periods=total_rows, freq=freq)
    # Preserve original formatting (date only or datetime)
    sample_val = df[ts_col].iloc[0]
    has_time = len(str(sample_val)) > 10
    fmt = '%Y-%m-%d %H:%M:%S' if has_time else '%Y-%m-%d'
    df[ts_col] = clean_range.strftime(fmt)
    # Save the repaired CSV
    clean_path = os.path.splitext(csv_path)[0] + OUTPUT_SUFFIX + '.csv'
    df.to_csv(clean_path, index=False)
    # Record a snippet around the corruption point for the report
    if corrupted_idx is not None:
        fixed_snippet = capture_snippet(df, corrupted_idx)
        orig_df = pd.read_csv(csv_path)
        original_snippet = capture_snippet(orig_df, corrupted_idx)
        report.append({
            'file': filename,
            'corrupted_line': int(corrupted_idx) + 2,  # +2 accounts for header (line numbers start at 1)
            'original_snippet': original_snippet.to_dict(orient='list'),
            'fixed_snippet': fixed_snippet.to_dict(orient='list')
        })
    else:
        report.append({
            'file': filename,
            'corrupted_line': None,
            'original_snippet': None,
            'fixed_snippet': None
        })

# Write a simple human‑readable report
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
print('✅ All CSV timestamps repaired.')
print('Report saved to', report_path)
