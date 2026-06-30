import pandas as pd
import os
from influxdb_client import InfluxDBClient, WriteOptions

# InfluxDB Configuration
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "institutional_super_secret_token_2026"
INFLUX_ORG = "quant_fund"
INFLUX_BUCKET = "crypto_mtf"

def migrate_csv_to_influx(data_dir="data"):
    print(f"Connecting to InfluxDB at {INFLUX_URL}...")
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=600000)
    
    # Use native background batching specifically built to prevent OOM
    write_options = WriteOptions(batch_size=50000, flush_interval=10000, jitter_interval=2000, retry_interval=5000)
    
    timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1mo']
    assets = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
    
    with client.write_api(write_options=write_options) as write_api:
        # 1. Migrate Price/Volume Data
        for asset in assets:
            for tf in timeframes:
                filename = f"{asset}_{tf}_historical.csv"
                filepath = os.path.join(data_dir, filename)
                if os.path.exists(filepath):
                    print(f"Migrating {filename} to InfluxDB...")
                    df = pd.read_csv(filepath)
                    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
                    df = df.dropna(subset=['timestamp'])
                    df['asset'] = asset
                    df['timeframe'] = tf
                    df.set_index('timestamp', inplace=True)
                    
                    # InfluxDB client automatically chunks the dataframe based on WriteOptions
                    write_api.write(
                        bucket=INFLUX_BUCKET,
                        record=df,
                        data_frame_measurement_name='crypto_mtf_data',
                        data_frame_tag_columns=['asset', 'timeframe']
                    )
                    print(f"[OK] {filename} migration queued in background.")
                    
            # 2. Migrate Sentiment Data
            sentiment_file = f"{asset}_sentiment_2019_2026.csv"
            sentiment_path = os.path.join(data_dir, sentiment_file)
            if os.path.exists(sentiment_path):
                print(f"Migrating {sentiment_file} to InfluxDB...")
                sent_df = pd.read_csv(sentiment_path)
                sent_df['timestamp'] = pd.to_datetime(sent_df['timestamp'], utc=True, errors='coerce')
                sent_df = sent_df.dropna(subset=['timestamp'])
                sent_df['asset'] = asset
                sent_df.set_index('timestamp', inplace=True)
                
                write_api.write(
                    bucket=INFLUX_BUCKET,
                    record=sent_df,
                    data_frame_measurement_name='crypto_mtf_sentiment',
                    data_frame_tag_columns=['asset']
                )
                print(f"[OK] {sentiment_file} migration queued in background.")

    client.close()
    print("\n[SUCCESS] All CSV data has been migrated to the Institutional Time-Series Database!")

if __name__ == "__main__":
    migrate_csv_to_influx()
