import os, glob, pandas as pd

DATA_DIR = os.path.join(os.getcwd(), 'data')
OUTPUT_SUFFIX = '_clean'

def capture_snippet(df, idx, window=3):
    start = max(idx - window, 0)
    end = min(idx + window + 1, len(df))
    return df.iloc[start:end]

def infer_frequency(parsed):
    """Return a pandas frequency (Timedelta) for the series.
    Handles edge‑cases where diff mode is zero or infer_freq fails.
    """
    # Drop NaT and ensure at least two points
    valid = parsed.dropna()
    if len(valid) < 2:
        return pd.Timedelta(days=1)  # fallback
    # Try pandas' infer_freq (returns string like 'D', 'H', 'T')
    freq_str = pd.infer_freq(valid)
    if freq_str:
        try:
            return pd.tseries.frequencies.to_offset(freq_str)
        except Exception:
            pass
    # Use mode of differences
    diffs = valid.diff().dropna()
    if not diffs.empty:
        mode = diffs.mode()[0]
        if mode != pd.Timedelta(0):
            return mode
    # Fallback to first diff
    first_diff = valid.iloc[1] - valid.iloc[0]
    if first_diff != pd.Timedelta(0):
        return first_diff
    # Ultimate fallback – daily
    return pd.Timedelta(days=1)

report_lines = []

for csv_path in sorted(glob.glob(os.path.join(DATA_DIR, '*.csv'))):
    filename = os.path.basename(csv_path)
    df = pd.read_csv(csv_path)
    ts_col = 'timestamp' if 'timestamp' in df.columns else df.columns[0]
    # Parse timestamps, coerce errors to NaT
    parsed = pd.to_datetime(df[ts_col], errors='coerce', utc=True)
    # First corrupted index (first NaT after we have seen a valid timestamp)
    corrupted_idx = None
    if parsed.isna().any():
        # Find the first NaT that appears after at least one non‑NaT value
        first_valid_seen = False
        for i, val in enumerate(parsed):
            if pd.notnull(val):
                first_valid_seen = True
            elif first_valid_seen:
                corrupted_idx = i
                break
    # Determine the true start date (first non‑NaT)
    first_valid = parsed.dropna().iloc[0]
    total_rows = len(df)
    freq = infer_frequency(parsed)
    # Build clean date_range
    clean_range = pd.date_range(start=first_valid, periods=total_rows, freq=freq)
    # Preserve original format (date only vs datetime)
    sample_val = df[ts_col].iloc[0]
    has_time = len(str(sample_val)) > 10
    fmt = '%Y-%m-%d %H:%M:%S' if has_time else '%Y-%m-%d'
    df[ts_col] = clean_range.strftime(fmt)
    # Save cleaned file
    clean_path = os.path.splitext(csv_path)[0] + OUTPUT_SUFFIX + '.csv'
    df.to_csv(clean_path, index=False)

    # Build report snippet for this file
    if corrupted_idx is not None:
        orig_df = pd.read_csv(csv_path)
        orig_snip = capture_snippet(orig_df, corrupted_idx)
        fixed_snip = capture_snippet(df, corrupted_idx)
        report_lines.append(f"File: {filename}\n  First corrupted line: {corrupted_idx+2}\n  Original snippet around corruption:\n{orig_snip}\n  Fixed snippet around same rows:\n{fixed_snip}\n")
    else:
        report_lines.append(f"File: {filename}\n  No corruption detected.\n")

# Write a concise text report
report_path = os.path.join(os.getcwd(), 'scratch', 'timestamp_fix_report.txt')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(report_lines))
print('Timestamp repair completed for all CSVs.')
print('Report written to', report_path)
