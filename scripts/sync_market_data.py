import os
import pandas as pd
import ccxt
import time
from datetime import datetime

# Define our Universal Architecture parameters
ASSETS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
# Map CSV names to CCXT timeframe names
TIMEFRAMES = {
    '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
    '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h', '8h': '8h', '12h': '12h',
    '1d': '1d', '3d': '3d', '1w': '1w', '1mo': '1M'
}

def sync_data():
    print("[+] Initializing Binance CCXT Connection...")
    exchange = ccxt.binance({'enableRateLimit': True})
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    
    for asset in ASSETS:
        csv_asset = asset.replace('/', '')
        print(f"\n{'='*50}\n[*] Synchronizing Data for {asset}\n{'='*50}")
        
        for csv_tf, ccxt_tf in TIMEFRAMES.items():
            filepath = os.path.join(data_dir, f"{csv_asset}_{csv_tf}_historical.csv")
            
            if not os.path.exists(filepath):
                print(f"  [!] Missing file {filepath}. Skipping...")
                continue
                
            try:
                # Read just the very last line to find where we left off
                # Using tail equivalent in pandas to be memory efficient
                df_tail = pd.read_csv(filepath).tail(1)
                
                if df_tail.empty:
                    continue
                    
                last_time_str = df_tail['timestamp'].iloc[0]
                last_time_dt = pd.to_datetime(last_time_str, utc=True)
                since_ms = int(last_time_dt.timestamp() * 1000)
                
                # Fetch missing data from the exchange
                new_data = []
                current_since = since_ms
                
                while True:
                    try:
                        ohlcv = exchange.fetch_ohlcv(asset, timeframe=ccxt_tf, since=current_since, limit=1000)
                        if not ohlcv or len(ohlcv) <= 1:
                            break # No new data
                            
                        # Avoid duplicating the very last row
                        if ohlcv[0][0] <= current_since:
                            ohlcv = ohlcv[1:]
                            if not ohlcv: break
                            
                        new_data.extend(ohlcv)
                        current_since = ohlcv[-1][0]
                        time.sleep(exchange.rateLimit / 1000) # Respect rate limits
                    except Exception as e:
                        print(f"    [!] Error fetching {ccxt_tf}: {e}")
                        break
                        
                if new_data:
                    new_df = pd.DataFrame(new_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    new_df['timestamp'] = pd.to_datetime(new_df['timestamp'], unit='ms', utc=True)
                    
                    # Convert to our strict ISO8601 format to match the massive fix we did earlier
                    new_df['timestamp'] = new_df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
                    
                    # Append to CSV safely
                    new_df.to_csv(filepath, mode='a', header=False, index=False)
                    print(f"  [OK] {csv_tf:<4} | Appended {len(new_df)} new candles (Up to {new_df['timestamp'].iloc[-1]})")
                else:
                    print(f"  [OK] {csv_tf:<4} | Already up to date.")
                    
            except Exception as e:
                print(f"  [!] Failed processing {filepath}: {e}")

if __name__ == "__main__":
    sync_data()
    print("\n[SUCCESS] Market Data Synchronization Complete. You are ready to retrain the Universal Brain!")
