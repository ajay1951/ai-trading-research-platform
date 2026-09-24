import ccxt
from datetime import datetime, timezone

exchange = ccxt.binance({'enableRateLimit': True})
start_dt = datetime(2019, 1, 1, tzinfo=timezone.utc)
start_ms = int(start_dt.timestamp() * 1000)

for sym in ["DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "SUI/USDT"]:
    try:
        ohlcv = exchange.fetch_ohlcv(sym, timeframe='1h', since=start_ms, limit=5)
        if ohlcv:
            first_ts = datetime.fromtimestamp(ohlcv[0][0]/1000, tz=timezone.utc)
            print(f"{sym}: First candle = {first_ts}, total returned = {len(ohlcv)}")
        else:
            print(f"{sym}: returned empty with since={start_ms}")
    except Exception as e:
        print(f"{sym}: error {e}")
