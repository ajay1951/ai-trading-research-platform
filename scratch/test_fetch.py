import ccxt
import time

exchange = ccxt.binance({'enableRateLimit': True})
try:
    print("Fetching DOGE/USDT 1h...")
    ohlcv = exchange.fetch_ohlcv("DOGE/USDT", timeframe="1h", limit=5)
    print("Success! Got", len(ohlcv), "bars. Sample:", ohlcv[0])
except Exception as e:
    print("Binance fetch error:", type(e), e)
    
    # Try Bybit or Kraken as fallback if Binance spot has geo restrictions
    try:
        print("\nTrying Bybit fallback...")
        bybit = ccxt.bybit({'enableRateLimit': True})
        ohlcv_bybit = bybit.fetch_ohlcv("DOGE/USDT", timeframe="1h", limit=5)
        print("Bybit success! Got", len(ohlcv_bybit), "bars.")
    except Exception as e2:
        print("Bybit error:", type(e2), e2)
