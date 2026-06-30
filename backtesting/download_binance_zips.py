import os
import requests
import zipfile
import pandas as pd
from io import BytesIO
from datetime import datetime
from dateutil.relativedelta import relativedelta
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Standard columns for Binance Vision Spot Klines
COLUMNS = [
    'open_time', 'open', 'high', 'low', 'close', 'volume', 
    'close_time', 'quote_asset_volume', 'number_of_trades', 
    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
]

def fetch_and_parse_month(symbol, timeframe, date_str):
    """Worker function to download and parse a single month."""
    base_url = "https://data.binance.vision/data/spot/monthly/klines"
    filename = f"{symbol}-{timeframe}-{date_str}.zip"
    url = f"{base_url}/{symbol}/{timeframe}/{filename}"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with zipfile.ZipFile(BytesIO(response.content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f, names=COLUMNS)
                    # Keep OHLCV + Quote Volume
                    df = df[['open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_asset_volume']]
                    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
                    df.drop('open_time', axis=1, inplace=True)
                    df.set_index('timestamp', inplace=True)
                    return date_str, df
        elif response.status_code == 404:
            return date_str, None # Not found (expected for dates before coin existed)
        else:
            print(f"\n[!] Warning: {url} returned status {response.status_code}")
            return date_str, None
    except Exception as e:
        print(f"\n[!] Error fetching {date_str}: {e}")
        return date_str, None

def download_binance_monthly_klines(symbol, timeframe, start_date, end_date, max_workers=10):
    """
    Downloads monthly Kline (OHLCV) zip files asynchronously,
    combines them, and saves to CSV.
    """
    clean_symbol = symbol.replace("/", "").upper()
    
    current_date = datetime.strptime(start_date, "%Y-%m")
    end_date_obj = datetime.strptime(end_date, "%Y-%m")
    
    # Generate list of all months to download
    months_to_fetch = []
    while current_date <= end_date_obj:
        months_to_fetch.append(current_date.strftime("%Y-%m"))
        current_date += relativedelta(months=1)
        
    print(f"Queueing {len(months_to_fetch)} months for {clean_symbol} {timeframe}...")
    
    dataframes = []
    
    # Use ThreadPoolExecutor for concurrent downloads
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_date = {
            executor.submit(fetch_and_parse_month, clean_symbol, timeframe, date_str): date_str 
            for date_str in months_to_fetch
        }
        
        # Process results as they complete
        completed = 0
        for future in as_completed(future_to_date):
            date_str = future_to_date[future]
            completed += 1
            try:
                result_date, df = future.result()
                if df is not None:
                    dataframes.append(df)
                    print(f"[{completed}/{len(months_to_fetch)}] \u2713 Successfully loaded {date_str}")
                else:
                    print(f"[{completed}/{len(months_to_fetch)}] \u2717 Skipped {date_str} (Not Found)")
            except Exception as e:
                print(f"[{completed}/{len(months_to_fetch)}] \u2717 Exception for {date_str}: {e}")

    if not dataframes:
        print("No data was downloaded for this timeframe.")
        return
        
    print("Combining and sorting dataframes...")
    final_df = pd.concat(dataframes)
    final_df.sort_index(inplace=True)
    
    os.makedirs('data', exist_ok=True)
    output_filename = f"data/{clean_symbol}_{timeframe}_historical.csv"
    final_df.to_csv(output_filename)
    print(f"\u2705 Success! Saved {len(final_df)} rows to {output_filename}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FAST Bulk Download Binance Vision Zips (Multi-threaded)")
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading pair symbol (e.g., BTCUSDT,ETHUSDT)')
    parser.add_argument('--timeframe', type=str, default='1m', help='Candle timeframe (1m, 1h, 1d, etc) or "all"')
    parser.add_argument('--start', type=str, default='2023-01', help='Start month YYYY-MM')
    parser.add_argument('--end', type=str, default='2023-12', help='End month YYYY-MM')
    parser.add_argument('--workers', type=int, default=15, help='Number of concurrent downloads (default 15)')
    
    args = parser.parse_args()
    
    symbols = [s.strip().upper() for s in args.symbol.split(',')]
    
    for symbol in symbols:
        print(f"\n{'#'*60}\nPROCESSING SYMBOL: {symbol}\n{'#'*60}")
        if args.timeframe.lower() == 'all':
            timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1mo']
            for tf in timeframes:
                print(f"\n{'='*50}\nStarting {tf} timeframe for {symbol}...\n{'='*50}")
                download_binance_monthly_klines(symbol, tf, args.start, args.end, max_workers=args.workers)
        else:
            tfs = [t.strip() for t in args.timeframe.split(',')]
            for tf in tfs:
                print(f"\n{'='*50}\nStarting {tf} timeframe for {symbol}...\n{'='*50}")
                download_binance_monthly_klines(symbol, tf, args.start, args.end, max_workers=args.workers)
