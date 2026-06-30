import ccxt
import pandas as pd
import time
import os
import argparse
from datetime import datetime, timedelta

def download_ohlcv(symbol, timeframe, since_days_ago, limit=1000):
    """
    Downloads historical OHLCV data using CCXT and saves it to a CSV.
    """
    exchange = ccxt.binance({'enableRateLimit': True})
    
    # Calculate the 'since' timestamp
    since = exchange.milliseconds() - (since_days_ago * 24 * 60 * 60 * 1000)
    
    print(f"Downloading {symbol} data for timeframe {timeframe}...")
    
    all_ohlcv = []
    
    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, limit)
            if not len(ohlcv):
                break
                
            all_ohlcv.extend(ohlcv)
            # Update 'since' to the last candle's timestamp + 1 ms to get the next batch
            since = ohlcv[-1][0] + 1
            
            print(f"Fetched {len(all_ohlcv)} candles so far...")
            
            # Don't exceed current time
            if since >= exchange.milliseconds():
                break
                
            time.sleep(exchange.rateLimit / 1000) # Respect rate limits
            
        except Exception as e:
            print(f"Error fetching data: {e}")
            break
            
    if not all_ohlcv:
        print("No data found.")
        return
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # Save to CSV
    os.makedirs('data', exist_ok=True)
    filename = f"data/{symbol.replace('/', '_')}_{timeframe}.csv"
    df.to_csv(filename)
    print(f"Saved {len(df)} rows to {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Historical Crypto Data")
    parser.add_argument('--symbol', type=str, default='BTC/USDT', help='Trading pair symbol')
    parser.add_argument('--days', type=int, default=365, help='Number of days of history to fetch')
    
    args = parser.parse_args()
    
    # Timeframes you want to fetch
    timeframes = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
    
    for tf in timeframes:
        download_ohlcv(args.symbol, tf, args.days)
