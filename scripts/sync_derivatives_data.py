import ccxt
import pandas as pd
import time
import os
from datetime import datetime

def fetch_derivatives_data(symbol="BTC/USDT", days=365):
    print(f"[+] Initializing Binance CCXT Connection for Derivatives...")
    
    # Enable futures/swap API
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap' # USD-M Futures
        }
    })
    
    since = exchange.milliseconds() - (days * 24 * 60 * 60 * 1000)
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    asset_name = symbol.replace("/", "")
    swap_symbol = f"{symbol}:USDT"
    
    # 1. Fetch Funding Rate History
    if exchange.has.get('fetchFundingRateHistory'):
        print(f"[*] Fetching Funding Rate History for {swap_symbol}...")
        funding_data = []
        current_since = since
        while True:
            try:
                # CCXT typically returns [{info, symbol, fundingRate, timestamp, datetime}, ...]
                rates = exchange.fetch_funding_rate_history(swap_symbol, since=current_since, limit=1000)
                if not rates:
                    break
                    
                funding_data.extend(rates)
                current_since = rates[-1]['timestamp'] + 1
                
                print(f"  Fetched {len(funding_data)} funding rates...")
                if current_since >= exchange.milliseconds():
                    break
                    
                time.sleep(exchange.rateLimit / 1000)
            except Exception as e:
                print(f"  [!] Error fetching funding rates: {e}")
                break
                
        if funding_data:
            df_fund = pd.DataFrame(funding_data)
            df_fund['timestamp'] = pd.to_datetime(df_fund['timestamp'], unit='ms', utc=True)
            df_fund['timestamp'] = df_fund['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
            df_fund = df_fund[['timestamp', 'fundingRate']]
            df_fund = df_fund.rename(columns={'fundingRate': 'funding_rate'})
            
            fund_path = os.path.join(data_dir, f"{asset_name}_funding.csv")
            df_fund.to_csv(fund_path, index=False)
            print(f"  [SUCCESS] Saved {len(df_fund)} funding rate records to {fund_path}")
            
    # 2. Fetch Open Interest History
    if exchange.has.get('fetchOpenInterestHistory'):
        print(f"[*] Fetching Open Interest History for {swap_symbol}...")
        oi_data = []
        current_since = since
        while True:
            try:
                oi = exchange.fetch_open_interest_history(swap_symbol, '5m', since=current_since, limit=500)
                if not oi:
                    break
                    
                oi_data.extend(oi)
                current_since = oi[-1]['timestamp'] + 1
                
                print(f"  Fetched {len(oi_data)} open interest records...")
                if current_since >= exchange.milliseconds():
                    break
                    
                time.sleep(exchange.rateLimit / 1000)
            except Exception as e:
                print(f"  [!] Error fetching open interest: {e}")
                break
                
        if oi_data:
            df_oi = pd.DataFrame(oi_data)
            df_oi['timestamp'] = pd.to_datetime(df_oi['timestamp'], unit='ms', utc=True)
            df_oi['timestamp'] = df_oi['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
            df_oi = df_oi[['timestamp', 'openInterestValue']]
            df_oi = df_oi.rename(columns={'openInterestValue': 'open_interest'})
            
            oi_path = os.path.join(data_dir, f"{asset_name}_oi.csv")
            df_oi.to_csv(oi_path, index=False)
            print(f"  [SUCCESS] Saved {len(df_oi)} open interest records to {oi_path}")

if __name__ == "__main__":
    assets = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    for a in assets:
        fetch_derivatives_data(a, days=365)
