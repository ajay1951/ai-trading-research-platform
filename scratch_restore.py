import ccxt
import pandas as pd
import time
import os

def restore_1d_data():
    symbol = "BTC/USDT"
    timeframe = "1d"
    # Let's restore the last 7 years of daily data
    since_days_ago = 365 * 7 
    
    print(f"Restoring {symbol} {timeframe} data from CCXT...")
    exchange = ccxt.binance({'enableRateLimit': True})
    since = exchange.milliseconds() - (since_days_ago * 24 * 60 * 60 * 1000)
    
    all_ohlcv = []
    
    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, 1000)
            if not len(ohlcv):
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            if since >= exchange.milliseconds():
                break
            time.sleep(exchange.rateLimit / 1000)
        except Exception as e:
            print(f"Error fetching data: {e}")
            break
            
    if not all_ohlcv:
        print("Failed to restore data.")
        return
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # InfluxDB and other scripts expect quote_asset_volume, let's just make it 0 for this restore
    df['quote_asset_volume'] = 0.0
    
    filename = "data/BTCUSDT_1d_historical.csv"
    df.to_csv(filename, index=False)
    print(f"Successfully restored {len(df)} rows to {filename}!")

if __name__ == "__main__":
    restore_1d_data()
