import csv
import os
from datetime import datetime

DATA_DIR = "data"
OUTPUT_FILE = os.path.join(DATA_DIR, "influx_seed.lp")

def parse_time_to_ns(time_str):
    """
    Parse a time string (mixed formats) to nanoseconds since epoch.
    Fast standard fallback.
    """
    try:
        if 'T' in time_str:
            # e.g. 2026-05-29T20:45:00+00:00
            time_str = time_str.split('+')[0].replace('Z', '')
            dt = datetime.fromisoformat(time_str)
        else:
            # e.g. 2019-06-01 00:00:00
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        
        return int(dt.timestamp() * 1_000_000_000)
    except Exception as e:
        return None

def convert_all():
    assets = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
    timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1mo']
    
    total_lines = 0
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
        print(f"[*] Writing Line Protocol to {OUTPUT_FILE}...")
        
        # 1. Price Data
        for asset in assets:
            for tf in timeframes:
                filepath = os.path.join(DATA_DIR, f"{asset}_{tf}_historical.csv")
                if not os.path.exists(filepath):
                    continue
                
                print(f"  -> Converting {asset} {tf}...")
                with open(filepath, 'r', encoding='utf-8') as in_f:
                    reader = csv.DictReader(in_f)
                    for row in reader:
                        ts_ns = parse_time_to_ns(row.get('timestamp', ''))
                        if not ts_ns: continue
                        
                        # InfluxDB Line Protocol: measurement,tag1=val1 field1=val1 timestamp_ns
                        lp = f"crypto_mtf_data,asset={asset},timeframe={tf} open={row['open']},high={row['high']},low={row['low']},close={row['close']},volume={row['volume']} {ts_ns}\n"
                        out_f.write(lp)
                        total_lines += 1
                        
        # 2. Sentiment Data
        for asset in assets:
            for sentiment_file in [f"{asset}_sentiment_2019_2026.csv", f"{asset}_sentiment_historical.csv", f"{asset}_sentiment_historical_2026.csv"]:
                filepath = os.path.join(DATA_DIR, sentiment_file)
                if not os.path.exists(filepath):
                    continue
                
                print(f"  -> Converting Sentiment {sentiment_file}...")
                with open(filepath, 'r', encoding='utf-8') as in_f:
                    reader = csv.DictReader(in_f)
                    for row in reader:
                        ts_ns = parse_time_to_ns(row.get('timestamp', ''))
                        if not ts_ns: continue
                        
                        # Build fields string dynamically for sentiment
                        fields = []
                        for k, v in row.items():
                            if k != 'timestamp' and k != 'asset':
                                try:
                                    float_val = float(v)
                                    fields.append(f"{k}={float_val}")
                                except:
                                    pass # Ignore non-numeric columns
                        
                        if fields:
                            lp = f"crypto_mtf_sentiment,asset={asset} {','.join(fields)} {ts_ns}\n"
                            out_f.write(lp)
                            total_lines += 1

    print(f"\n[+] Success! Converted {total_lines} lines to Line Protocol.")
    print(f"[+] Output saved to {OUTPUT_FILE} (Zero-RAM streaming method)")

if __name__ == "__main__":
    convert_all()
