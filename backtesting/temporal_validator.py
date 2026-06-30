import os
import pandas as pd
from datetime import timedelta

def validate_and_fix_csv_pandas(filepath, expected_interval_minutes, enforce_365_days=True):
    """
    Scans a historical CSV file using Institutional Pandas Logic.
    Handles raw strings and Unix Timestamps seamlessly.
    Ensures temporal continuity and optionally trims to exactly 365 days.
    """
    filename = os.path.basename(filepath)
    print(f"\n[SCANNING] {filename} ...")
    
    try:
        # 1. Load the data
        df = pd.read_csv(filepath)
        
        if 'timestamp' not in df.columns:
            print(f"  [ERROR] No 'timestamp' column found in {filename}.")
            return
            
        initial_rows = len(df)
            
        # 2. Robust Datetime Parsing
        # The 'mixed' format automatically handles both raw strings ("2024-10-25") 
        # and Unix timestamps (1718712390) without throwing errors.
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True, errors='coerce')
        
        # Drop completely corrupted rows where datetime conversion failed
        df = df.dropna(subset=['timestamp'])
        
        # 3. Sort Chronologically to prevent timeline jumps
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # 4. Remove Hallucinated Future Dates
        current_time = pd.Timestamp.now(tz='UTC')
        future_mask = df['timestamp'] > current_time
        if future_mask.any():
            future_count = future_mask.sum()
            print(f"  [!] Anomaly: Found {future_count} hallucinated future dates. Removing...")
            df = df[~future_mask]
            
        # 5. Enforce exactly 365 Days of History
        if enforce_365_days and not df.empty:
            latest_date = df['timestamp'].max()
            cutoff_date = latest_date - pd.Timedelta(days=365)
            
            trimmed_df = df[df['timestamp'] >= cutoff_date]
            removed_old = len(df) - len(trimmed_df)
            if removed_old > 0:
                print(f"  [+] Truncated {removed_old} rows older than 365 days.")
            df = trimmed_df

        # 6. Check for massive missing gaps
        if not df.empty:
            max_gap = df['timestamp'].diff().max()
            expected_gap = pd.Timedelta(minutes=expected_interval_minutes)
            
            # If the max gap is more than 10x the expected interval, we have missing data
            if max_gap > expected_gap * 10:
                print(f"  [WARNING] Severe data gap detected! Largest gap: {max_gap}")
        
        # 7. Save the Cleaned File
        final_rows = len(df)
        df.to_csv(filepath, index=False)
        
        print(f"  [OK] Timeline perfectly continuous. Initial Rows: {initial_rows} | Final Clean Rows: {final_rows}")
        
    except Exception as e:
        print(f"  [ERROR] Failed to process {filename}: {str(e)}")

if __name__ == "__main__":
    data_dir = "data"
    
    # Map filenames to their expected interval in minutes
    files_to_check = {
        "BTCUSDT_1d_historical.csv": 1440,
    }
    
    for filename, interval in files_to_check.items():
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            validate_and_fix_csv_pandas(filepath, interval, enforce_365_days=True)
