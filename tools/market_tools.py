import asyncio
import logging
import ccxt
import ccxt.pro as ccxtpro
from core.memory import SharedMemory

logger = logging.getLogger(__name__)

class WebSocketMarketStream:
    """
    High-Frequency Market Data Streamer.
    Uses ccxt.pro WebSockets to continuously push real-time updates to SharedMemory.
    """
    def __init__(self, memory: SharedMemory = None):
        self.memory = memory or SharedMemory()
        self.exchange = ccxtpro.binance({
            'enableRateLimit': True,
        })
        self._is_running = False

    async def stream_ticker(self, symbol: str):
        """Continuously streams ticker data via WebSocket without blocking."""
        self._is_running = True
        logger.info(f"Starting WS ticker stream for {symbol}")
        
        while self._is_running:
            try:
                # Await real-time push from the exchange via WebSocket
                ticker = await self.exchange.watch_ticker(symbol)
                
                # Clean and structure data
                clean_data = {
                    "symbol": symbol,
                    "price": ticker.get('last'),
                    "high": ticker.get('high'),
                    "low": ticker.get('low'),
                    "volume": ticker.get('quoteVolume'),
                    "change_pct": ticker.get('percentage'),
                    "timestamp": ticker.get('timestamp')
                }
                
                # Instantly pipe to SharedMemory for Fast Lane agents
                self.memory.store(f"market_data:{symbol}", clean_data, agent="market_stream")
                self.memory.publish("market_data_update", clean_data, sender="market_stream")
                
            except ccxt.NetworkError as e:
                logger.warning(f"Network error in WS stream: {e}. Auto-reconnecting in 1s...")
                await asyncio.sleep(1)
            except ccxt.ExchangeError as e:
                logger.warning(f"Exchange error in WS stream: {e}. Auto-reconnecting in 2s...")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Unexpected error in WS stream: {e}. Auto-reconnecting in 5s...")
                await asyncio.sleep(5)
                
    async def close(self):
        """Gracefully close the WebSocket connection."""
        self._is_running = False
        await self.exchange.close()

# Singleton instance for system-wide access
market_stream = WebSocketMarketStream()