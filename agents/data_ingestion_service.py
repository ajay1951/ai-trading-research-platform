"""
Standalone Data Ingestion Service for SENTINEL AI.

This service continuously fetches market data for specified symbols and
publishes it to a Redis Pub/Sub channel, forming the backbone of the
event-driven architecture.
"""
import asyncio
import json
import os
import sys
from typing import List

# Add project root to the Python path to allow importing from 'agents'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import redis.asyncio as redis
from agents.data_agent import WebSocketMarketData

# --- Configuration ---
SYMBOLS_TO_TRACK = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
TIMEFRAME = "1m"
FETCH_INTERVAL_SECONDS = 60  # Fetch every minute
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = 6379

async def main():
    """
    Main loop for the data ingestion service.
    Fetches market data for specified symbols and publishes it to Redis.
    """
    print("--- Starting Data Ingestion Service ---")
    print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}")
    try:
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        await redis_client.ping()
        print("Redis connection successful.")
    except Exception as e:
        print(f"FATAL: Could not connect to Redis. Exiting. Error: {e}")
        return

    data_fetcher = WebSocketMarketData()
    print(f"Tracking symbols: {', '.join(SYMBOLS_TO_TRACK)}")
    print(f"Timeframe: {TIMEFRAME}, Fetch Interval: {FETCH_INTERVAL_SECONDS}s")

    while True:
        for symbol in SYMBOLS_TO_TRACK:
            try:
                print(f"Fetching {TIMEFRAME} OHLCV data for {symbol}...")
                # Fetch last 2 candles to ensure we have the latest complete one
                ohlcv_data = await data_fetcher.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=2)

                if not ohlcv_data:
                    print(f"Warning: No data returned for {symbol}")
                    continue

                latest_candle = ohlcv_data[-1]

                payload = {
                    "symbol": latest_candle.symbol, "exchange": latest_candle.exchange,
                    "timeframe": latest_candle.timeframe, "timestamp": latest_candle.timestamp.isoformat(),
                    "open": latest_candle.open, "high": latest_candle.high,
                    "low": latest_candle.low, "close": latest_candle.close, "volume": latest_candle.volume,
                }
                payload_json = json.dumps(payload)

                channel = f"market_data:{TIMEFRAME}:{symbol.replace('/', '_')}"
                await redis_client.publish(channel, payload_json)
                print(f"Published to {channel}")
            except Exception as e:
                print(f"ERROR: An error occurred while fetching data for {symbol}: {e}")
        print(f"--- Cycle complete. Waiting for {FETCH_INTERVAL_SECONDS} seconds... ---")
        await asyncio.sleep(FETCH_INTERVAL_SECONDS)

if __name__ == "__main__":
    asyncio.run(main())