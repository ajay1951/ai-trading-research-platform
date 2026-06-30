import asyncio
import logging
import json
import os
import ccxt
import math
import random
import ccxt.pro as ccxtpro
from core.memory import SharedMemory

logger = logging.getLogger(__name__)

class WebSocketExecutionStream:
    """
    Asynchronous Order Execution Daemon.
    Uses ccxt.pro to route orders via authenticated WebSocket streams.
    """
    def __init__(self, memory: SharedMemory = None):
        self.memory = memory or SharedMemory()
        
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        
        self.exchange = ccxtpro.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {
                'defaultType': 'spot',
            },
            'enableRateLimit': True,
        })
        self.order_queue = asyncio.Queue()
        self._is_running = False

    async def start_listening(self):
        """Continuously pulls payloads from the order queue and dispatches them via WebSocket."""
        self._is_running = True
        logger.info("Starting WS Execution listener.")
        
        while self._is_running:
            try:
                trade_payload = await self.order_queue.get()
                await self._process_order(trade_payload)
                self.order_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in execution loop: {e}")
                await asyncio.sleep(1)

    async def submit_order(self, trade_data: dict):
        """Public method to push orders to the execution daemon's queue."""
        await self.order_queue.put(trade_data)

    async def _process_order(self, data: dict):
        action = data.get("action", "").upper()
        mode = data.get("mode", "paper")

        if action == "LIQUIDATE_ALL":
            logger.warning("🚨 EMERGENCY: LIQUIDATE_ALL trigger received! Bypassing all guardrails!")
            if mode == "paper":
                await self._execute_paper_liquidate_all(data)
            elif mode == "live":
                await self._execute_live_liquidate_all(data)
            return

        amount = data.get("amount")
        if action not in ["BUY", "SELL"]:
            logger.error(f"Invalid action: {action}. Must be BUY, SELL, or LIQUIDATE_ALL.")
            return
        if not amount:
            logger.error("Error: 'amount' is a required field.")
            return

        entry_price = data.get("price") or data.get("entry_price")
        symbol = data.get("symbol", "UNKNOWN").upper()
        
        if entry_price is None and symbol != "UNKNOWN":
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                entry_price = ticker.get('last')
            except Exception as e:
                logger.warning(f"Could not fetch ticker for {symbol}: {e}")

        if entry_price is not None and float(amount) * float(entry_price) > 1000 and not data.get("twap_override"):
            order_value = float(amount) * float(entry_price)
            logger.info(f"Order value ${order_value:.2f} > $1000. Diverting to TWAP algorithm.")
            asyncio.create_task(self._execute_twap_block(data, order_value, float(entry_price)))
            return
            
        # Enforce strict asymmetric Risk/Reward ratio
        stop_loss = data.get("stop_loss")
        take_profit = data.get("take_profit")
        
        if stop_loss is not None and take_profit is not None and entry_price is not None:
            risk = abs(float(entry_price) - float(stop_loss))
            reward = abs(float(take_profit) - float(entry_price))
            if risk > 0:
                rr_ratio = reward / risk
                if rr_ratio < 2.5:
                    logger.error(f"Order rejected: Risk/Reward ratio {rr_ratio:.2f} is below the strict 2.5x threshold.")
                    return

        if mode == "paper":
            await self._execute_paper_trade(data)
        elif mode == "live":
            await self._execute_live_trade(data)
        else:
            logger.error(f"Invalid mode: '{mode}'. Must be 'paper' or 'live'.")

    async def _execute_paper_trade(self, data: dict):
        """Logs a trade to a file for paper trading."""
        from datetime import datetime
        action = data.get("action", "").upper()
        symbol = data.get("symbol", "UNKNOWN").upper()
        stop_loss = data.get("stop_loss")
        take_profit = data.get("take_profit")
        amount = data.get("amount")

        trade_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "symbol": symbol,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "amount": amount,
            "status": "PAPER_TRADE_EXECUTED",
        }

        file_path = "paper_trades_log.json"
        
        trades = []
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                try:
                    trades = json.load(f)
                except json.JSONDecodeError:
                    trades = []

        trades.append(trade_record)

        with open(file_path, "w") as f:
            json.dump(trades, f, indent=4)

        logger.info(f"Paper trade executed: {action} {amount} of {symbol}")
        self.memory.publish("trade_executed", trade_record, sender="execution_stream")

    async def _execute_live_trade(self, data: dict):
        """Executes a live trade on an exchange using CCXT WebSockets/Async."""
        if not self.exchange.apiKey or not self.exchange.secret:
            logger.error("BINANCE_API_KEY and BINANCE_API_SECRET must be set for live trading.")
            return

        symbol = data['symbol']
        order_type = data.get('type', 'market')
        side = data['action'].lower()
        amount = data['amount']
        price = data.get('price')

        try:
            # CCXT Pro gracefully handles authenticated WS order submission under the hood
            order = await self.exchange.create_order(symbol, order_type, side, amount, price)
            logger.info(f"Live trade executed via WS: {order['side'].upper()} {order['symbol']} for amount {order['amount']}. ID: {order['id']}")
            self.memory.publish("trade_executed", order, sender="execution_stream")
            
        except ccxt.NetworkError as e:
            logger.warning(f"Network error during live WS execution: {e}. Not retrying to prevent dupe orders.")
        except ccxt.ExchangeError as e:
            logger.warning(f"Exchange rejected WS order: {e}")
            logger.error(f"Live WS execution failed completely: {e}")

    async def _execute_twap_block(self, data: dict, total_value: float, current_price: float):
        """Asynchronously slices a large order into TWAP micro-orders to minimize market impact."""
        from core.orchestrator import coordinator
        
        action = data.get("action", "").upper()
        symbol = data.get("symbol")
        total_amount = float(data.get("amount"))
        mode = data.get("mode", "paper")
        
        # Slice into roughly $100 chunks
        num_chunks = max(1, int(math.ceil(total_value / 100.0)))
        chunk_amount = total_amount / num_chunks
        
        # Space out randomly over 5-10 minutes (300 to 600 seconds)
        total_duration = random.uniform(300, 600)
        base_interval = total_duration / num_chunks if num_chunks > 1 else 0
            
        logger.info(f"Starting TWAP for {symbol}: {num_chunks} chunks, ~{base_interval:.1f}s apart, total ~{total_duration/60:.1f}m.")
        
        executed_chunks = []
        total_executed_amount = 0.0
        total_cost = 0.0
        
        for i in range(num_chunks):
            if getattr(coordinator, 'is_halted', False):
                logger.critical(f"🚨 CIRCUIT BREAKER TRIPPED mid-TWAP! Aborting remaining {num_chunks - i} chunks.")
                break
                
            chunk_data = data.copy()
            chunk_data["amount"] = chunk_amount
            chunk_data["twap_override"] = True  # Prevent recursive TWAP
            
            try:
                chunk_exec_price = current_price
                if mode == "live":
                    if not self.exchange.apiKey or not self.exchange.secret:
                        logger.error("API keys missing for live TWAP chunk.")
                        break
                    order_type = data.get('type', 'market')
                    side = action.lower()
                    
                    order = await self.exchange.create_order(symbol, order_type, side, chunk_amount)
                    chunk_exec_price = order.get('average') or order.get('price') or current_price
                    logger.info(f"TWAP Chunk {i+1}/{num_chunks} Live: {side.upper()} {chunk_amount} @ {chunk_exec_price}")
                else:
                    logger.info(f"TWAP Chunk {i+1}/{num_chunks} Paper: {action} {chunk_amount}")
                    
                total_executed_amount += chunk_amount
                total_cost += chunk_amount * float(chunk_exec_price)
                
            except Exception as e:
                logger.error(f"TWAP chunk execution failed: {e}")
                
            if i < num_chunks - 1:
                # Sleep for base interval with some randomness (+/- 20%)
                jitter = random.uniform(0.8, 1.2)
                sleep_time = base_interval * jitter
                await asyncio.sleep(sleep_time)
                
        if total_executed_amount > 0:
            blended_price = total_cost / total_executed_amount
            consolidated_payload = {
                "action": action,
                "symbol": symbol,
                "amount": total_executed_amount,
                "price": blended_price,
                "status": "TWAP_COMPLETED",
                "chunks": num_chunks
            }
            self.memory.publish("trade_executed", consolidated_payload, sender="execution_stream_twap")
            logger.info(f"✅ TWAP Complete: {action} {total_executed_amount} {symbol} @ avg {blended_price:.4f}")

    async def _execute_paper_liquidate_all(self, data: dict):
        """Virtually liquidates all paper trading positions."""
        logger.info("🚨 EMERGENCY LIQUIDATION (PAPER): All open positions virtually liquidated to USDT.")
        self.memory.publish("trade_executed", {"status": "LIQUIDATED", "action": "LIQUIDATE_ALL"}, sender="execution_stream")

    async def _execute_live_liquidate_all(self, data: dict):
        """Cancel all open orders and market sell all non-USDT balances."""
        if not self.exchange.apiKey or not self.exchange.secret:
            logger.error("API keys missing for live liquidation.")
            return
        
        try:
            logger.warning("🚨 FETCHING BALANCES FOR EMERGENCY LIQUIDATION...")
            balance = await self.exchange.fetch_balance()
            for currency, val in balance['free'].items():
                if currency not in ['USDT', 'USD', 'USDC'] and val > 0:
                    symbol = f"{currency}/USDT"
                    try:
                        # Cancel open orders
                        open_orders = await self.exchange.fetch_open_orders(symbol)
                        for order in open_orders:
                            await self.exchange.cancel_order(order['id'], symbol)
                        
                        # Market sell the entire available balance
                        order = await self.exchange.create_order(symbol, 'market', 'sell', val)
                        logger.info(f"🚨 EMERGENCY LIQUIDATION: Sold {val} of {symbol}")
                    except Exception as e:
                        logger.warning(f"Could not liquidate {symbol}: {e}")
            logger.warning("🚨 EMERGENCY LIQUIDATION COMPLETE.")
        except Exception as e:
            logger.error(f"Emergency Liquidation Failed: {e}")

    async def close(self):
        """Gracefully close the WebSocket connection."""
        self._is_running = False
        await self.exchange.close()

# Singleton instance
execution_stream = WebSocketExecutionStream()