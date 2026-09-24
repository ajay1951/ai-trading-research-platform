import os
import sys
import time
import pandas as pd
import ccxt
from datetime import datetime, timezone

EXPANDED_ASSETS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "NEAR/USDT",
    "LTC/USDT", "DOT/USDT", "SUI/USDT"
]

def fetch_universe_data(timeframe='1h', max_days=1800):
    print(f"[+] Initializing Binance Public Connection for {len(EXPANDED_ASSETS)} assets ({timeframe})...", flush=True)
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    # Calculate starting timestamp (e.g. 2020-01-01 or max_days ago)
    start_dt = datetime(2019, 1, 1, tzinfo=timezone.utc)
    start_ms = int(start_dt.timestamp() * 1000)
    
    for symbol in EXPANDED_ASSETS:
        clean_name = symbol.replace('/', '')
        filepath = os.path.join(data_dir, f"{clean_name}_{timeframe}_historical.csv")
        
        # Check existing file
        existing_df = None
        current_since = start_ms
        if os.path.exists(filepath):
            try:
                existing_df = pd.read_csv(filepath)
                if not existing_df.empty and 'timestamp' in existing_df.columns:
                    last_ts = pd.to_datetime(existing_df['timestamp'].iloc[-1], utc=True, format='ISO8601', errors='coerce')
                    if pd.notna(last_ts):
                        current_since = int(last_ts.timestamp() * 1000) + 1
                        print(f"[*] {clean_name}: Found {len(existing_df):,} existing rows up to {last_ts}.", flush=True)
                    if len(existing_df) >= 40000:
                        print(f"  [+] {clean_name} is already sufficiently historical ({len(existing_df):,} rows). Ready.", flush=True)
                        continue
            except Exception as e:
                print(f"[!] Error reading {filepath}: {e}")
                
        # Fetch missing batches
        new_rows = []
        now_ms = exchange.milliseconds()
        
        # If file already has 30,000+ rows and is up to 2026, we don't need endless fetch
        if existing_df is not None and len(existing_df) > 35000 and (now_ms - current_since) < (7 * 24 * 3600 * 1000):
            print(f"  [+] {clean_name} is already up to date ({len(existing_df):,} rows).", flush=True)
            continue
            
        print(f"  [->] Downloading {clean_name} {timeframe} batches from exchange...", flush=True)
        fetch_count = 0
        while current_since < now_ms and fetch_count < 60: # Limit to max 60k bars per run
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=current_since, limit=1000)
                if not ohlcv or len(ohlcv) <= 1:
                    break
                new_rows.extend(ohlcv)
                current_since = ohlcv[-1][0] + 1
                fetch_count += 1
                time.sleep(0.05) # Polite rate limit
            except Exception as e:
                print(f"  [!] Fetch warning for {symbol}: {e}")
                time.sleep(1)
                break
                
        if new_rows:
            df_new = pd.DataFrame(new_rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_new['timestamp'] = pd.to_datetime(df_new['timestamp'], unit='ms', utc=True)
            
            if existing_df is not None and not existing_df.empty:
                existing_df['timestamp'] = pd.to_datetime(existing_df['timestamp'], utc=True, format='ISO8601', errors='coerce')
                combined = pd.concat([existing_df, df_new]).dropna(subset=['timestamp']).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            else:
                combined = df_new
                
            combined.to_csv(filepath, index=False)
            print(f"  [+] Saved {clean_name}: Total {len(combined):,} candles.", flush=True)
        else:
            print(f"  [+] {clean_name} ready ({len(existing_df) if existing_df is not None else 0:,} candles).", flush=True)

    print("\n[+] Universe Data Synchronization Complete!", flush=True)

if __name__ == "__main__":
    fetch_universe_data(timeframe='1h')
