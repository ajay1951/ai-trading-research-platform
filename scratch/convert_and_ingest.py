import pandas as pd
import os
import glob
import subprocess

def main():
    data_dir = os.path.join(os.getcwd(), 'data')
    scratch_dir = os.path.join(os.getcwd(), 'scratch')
    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    
    # Command to pipe directly into InfluxDB container
    cmd = [
        'docker', 'exec', '-i', 'influxdb', 'influx', 'write', 
        '--bucket', 'crypto_mtf', 
        '--org', 'quant_fund', 
        '--token', 'institutional_super_secret_token_2026'
    ]

    print(f"Found {len(csv_files)} files to ingest. Starting Line Protocol pipeline...")

    for filepath in csv_files:
        filename = os.path.basename(filepath)
        parts = filename.replace('.csv', '').split('_')
        asset = parts[0]
        is_sentiment = "sentiment" in filename
        tf = parts[1] if not is_sentiment else "none"
        
        lp_path = os.path.join(scratch_dir, "temp_ingest.lp")
        if os.path.exists(lp_path):
            os.remove(lp_path)
            
        print(f"[{filename}] Converting & Ingesting...", end=" ", flush=True)
        try:
            # Read in memory-safe chunks (200,000 rows at a time)
            chunk_size = 200000
            for i, chunk in enumerate(pd.read_csv(filepath, chunksize=chunk_size)):
                chunk = chunk.dropna(subset=['timestamp'])
                timestamps = pd.to_datetime(chunk['timestamp'], utc=True, errors='coerce')
                valid_idx = timestamps.notnull()
                chunk = chunk[valid_idx]
                timestamps = timestamps[valid_idx].astype('int64')
                
                if is_sentiment:
                    lines = (
                        f"crypto_mtf_sentiment,asset={asset} " +
                        "sentiment_score=" + chunk['sentiment_score'].astype(str) + " " +
                        timestamps.astype(str)
                    )
                else:
                    lines = (
                        f"crypto_mtf_data,asset={asset},timeframe={tf} " +
                        "open=" + chunk['open'].astype(str) + "," +
                        "high=" + chunk['high'].astype(str) + "," +
                        "low=" + chunk['low'].astype(str) + "," +
                        "close=" + chunk['close'].astype(str) + "," +
                        "volume=" + chunk['volume'].astype(str) + " " +
                        timestamps.astype(str)
                    )
                
                # Write .lp text file to disk
                with open(lp_path, "w") as f:
                    f.write("\n".join(lines) + "\n")
                    
                # Stream the file directly into Docker instantly
                with open(lp_path, "rb") as f:
                    subprocess.run(cmd, stdin=f, check=True)
                    
            # Delete temporary file immediately to save disk space
            if os.path.exists(lp_path):
                os.remove(lp_path)
                
            print("OK!")
            
        except Exception as e:
            print(f"FAILED: {str(e)}")

    print("\n[SUCCESS] Line Protocol bulk-ingestion finished completely!")

if __name__ == "__main__":
    main()
