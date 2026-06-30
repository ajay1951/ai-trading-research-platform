import pandas as pd
import os
import concurrent.futures
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "institutional_super_secret_token_2026"
INFLUX_ORG = "quant_fund"
INFLUX_BUCKET = "crypto_mtf"

def process_file(task_info):
    filepath, asset, tf, is_sentiment = task_info
    
    if not os.path.exists(filepath):
        return
        
    print(f"[{asset} - {tf}] Starting ingest...")
    # Create a fresh client per process
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=60000)
    # Use synchronous mode to prevent timeout backpressure
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    chunk_size = 10000
    try:
        for i, chunk in enumerate(pd.read_csv(filepath, chunksize=chunk_size)):
            chunk['timestamp'] = pd.to_datetime(chunk['timestamp'], utc=True, errors='coerce')
            chunk = chunk.dropna(subset=['timestamp'])
            chunk['asset'] = asset
            chunk.set_index('timestamp', inplace=True)
            
            if is_sentiment:
                write_api.write(
                    bucket=INFLUX_BUCKET,
                    record=chunk,
                    data_frame_measurement_name='crypto_mtf_sentiment',
                    data_frame_tag_columns=['asset']
                )
            else:
                chunk['timeframe'] = tf
                write_api.write(
                    bucket=INFLUX_BUCKET,
                    record=chunk,
                    data_frame_measurement_name='crypto_mtf_data',
                    data_frame_tag_columns=['asset', 'timeframe']
                )
            if i % 10 == 0 and i > 0:
                print(f"[{asset} - {tf}] Ingested {i * chunk_size} rows...")
                
        print(f"[OK] {os.path.basename(filepath)} fully ingested.")
    except Exception as e:
        print(f"[ERROR] {os.path.basename(filepath)} failed: {str(e)}")
    finally:
        client.close()

def main():
    data_dir = os.path.join(os.getcwd(), 'data')
    timeframes = ['1mo', '1w', '3d', '1d', '12h', '8h', '6h', '4h', '2h', '1h', '30m', '15m', '5m', '3m', '1m']
    assets = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
    
    tasks = []
    
    for asset in assets:
        for tf in timeframes:
            filepath = os.path.join(data_dir, f"{asset}_{tf}_historical.csv")
            if os.path.exists(filepath):
                tasks.append((filepath, asset, tf, False))
                
        sent_path = os.path.join(data_dir, f"{asset}_sentiment_2019_2026.csv")
        if os.path.exists(sent_path):
            tasks.append((sent_path, asset, "sentiment", True))
            
    print(f"Found {len(tasks)} files to ingest.")
    
    # Run sequentially (1 worker) to prevent Docker from running out of RAM
    with concurrent.futures.ProcessPoolExecutor(max_workers=1) as executor:
        executor.map(process_file, tasks)

    print("\n[SUCCESS] Fast batch ingestion completed successfully!")

if __name__ == "__main__":
    main()
