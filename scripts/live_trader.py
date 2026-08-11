import os
import sys
import asyncio
import time
import ccxt
import ccxt.pro as ccxtpro
import pandas as pd
import numpy as np
import torch
import json
import redis
import yaml
import logging
from typing import List, Dict, Any, Tuple
from collections import deque
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Setup Advanced Logging
os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'logs'), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'logs', 'trading.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))
from meta_agent import MetaAgent
from risk_agent import RiskAgent
from sentiment_agent import SentimentAgent

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tools'))
from news_tools import fetch_news

class AsyncPaperTrader:
    def __init__(self, config_path: str = "config.yaml") -> None:
        # Load Centralized Configuration
        full_config_path = os.path.join(os.path.dirname(__file__), '..', config_path)
        with open(full_config_path, "r") as f:
            self.config = yaml.safe_load(f)
            
        self.assets: List[str] = self.config['trading']['universe']
        self.starting_cash: float = self.config['trading']['starting_cash']
        self.fee_rate: float = self.config['trading']['fee_rate']
        self.max_drawdown: float = self.config['trading']['max_drawdown_limit']
        self.news_interval: int = self.config['mlops']['news_scrape_interval']
        self.swing_model_path: str = self.config['mlops'].get('swing_model_path', 'models/weights/universal_meta_agent_15m.pth')
        self.intraday_model_path: str = self.config['mlops'].get('intraday_model_path', 'models/weights/universal_meta_agent_5m.pth')
        
        self.trading_mode: str = os.getenv('TRADING_MODE', 'PAPER').upper()
        
        logger.info(f"Booting Trading Engine in {self.trading_mode} Mode...")
        
        exchange_config = {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        }
        
        if self.trading_mode == 'LIVE':
            api_key = os.getenv('BINANCE_API_KEY')
            secret = os.getenv('BINANCE_API_SECRET')
            if not api_key or not secret:
                logger.error("LIVE mode selected but BINANCE_API_KEY or BINANCE_API_SECRET is missing!")
                sys.exit(1)
            exchange_config['apiKey'] = api_key
            exchange_config['secret'] = secret
            logger.warning("!!! LIVE TRADING ENABLED. REAL FUNDS ARE AT RISK !!!")
            
        self.exchange = ccxtpro.binance(exchange_config)
        
        logger.info("Loading Dual Universal AI Brains (Swing + Intraday)...")
        self.swing_brain = MetaAgent(input_dim=18, buffer_size=1000, batch_size=64)
        self.intraday_brain = MetaAgent(input_dim=18, buffer_size=1000, batch_size=64)
        
        full_swing_model_path = os.path.join(os.path.dirname(__file__), '..', self.swing_model_path)
        if os.path.exists(full_swing_model_path):
            self.swing_brain.q_network.load_state_dict(torch.load(full_swing_model_path, map_location=torch.device('cpu'), weights_only=True))
            self.swing_brain.q_network.eval()
            logger.info("Swing Neural Network Weights (15m) Loaded Successfully.")
        else:
            logger.warning(f"{self.swing_model_path} not found. Swing AI will trade randomly until trained.")
            
        full_intraday_model_path = os.path.join(os.path.dirname(__file__), '..', self.intraday_model_path)
        if os.path.exists(full_intraday_model_path):
            self.intraday_brain.q_network.load_state_dict(torch.load(full_intraday_model_path, map_location=torch.device('cpu'), weights_only=True))
            self.intraday_brain.q_network.eval()
            logger.info("Intraday Neural Network Weights (5m) Loaded Successfully.")
        else:
            logger.warning(f"{self.intraday_model_path} not found. Intraday AI will trade randomly until trained.")
            
        self.risk_manager = RiskAgent()
        self.sentiment_agent = SentimentAgent()
        
        self.news_cache: Dict[str, float] = {}
        self.last_news_time: Dict[str, float] = {}
        
        self.log_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'live_trades.csv')
        
        # Redis Connection for Crash Recovery
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        logger.info(f"Connecting to Redis at {redis_host} for State Recovery...")
        self.redis_client = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)
        
        # Kill Switch / Circuit Breaker Metrics
        self.error_count: int = 0
        self.kill_switch_activated: bool = False
        self.latest_prices: Dict[str, float] = {}
        
        self._init_files('15m')
        self._init_files('5m')

    def _init_files(self, timeframe: str) -> None:
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            pd.DataFrame(columns=['timestamp', 'asset', 'price', 'action', 'confidence', 'allocation', 'pnl']).to_csv(self.log_file, index=False)
            
        needs_reset = True
        redis_key = f"live_portfolio_{timeframe}"
        if self.redis_client.exists(redis_key):
            try:
                current_port = json.loads(self.redis_client.get(redis_key))
                # Half cash for each strategy
                if current_port.get("total_value", 0) >= ((self.starting_cash / 2) * self.max_drawdown):
                    needs_reset = False
            except Exception:
                pass
                
        if needs_reset:
            logger.info(f"Initializing or Resetting Portfolio for {timeframe}...")
            initial_portfolio = {
                "cash": self.starting_cash / 2, # Split cash 50/50
                "positions": {}, 
                "realized_pnl": 0.0,
                "total_value": self.starting_cash / 2
            }
            self.save_portfolio(initial_portfolio, timeframe)

    def load_portfolio(self, timeframe: str) -> Dict[str, Any]:
        redis_key = f"live_portfolio_{timeframe}"
        data = self.redis_client.get(redis_key)
        if data:
            return json.loads(str(data))
        return {"cash": self.starting_cash / 2, "positions": {}, "realized_pnl": 0.0, "total_value": self.starting_cash / 2}

    def save_portfolio(self, portfolio: Dict[str, Any], timeframe: str) -> None:
        redis_key = f"live_portfolio_{timeframe}"
        self.redis_client.set(redis_key, json.dumps(portfolio))

    async def emergency_liquidation(self, reason: str) -> None:
        if self.kill_switch_activated: return
        self.kill_switch_activated = True
        
        logger.error("="*80)
        logger.error("!!! CRITICAL ALERT: CIRCUIT BREAKER TRIGGERED !!!")
        logger.error(f"Reason: {reason}")
        logger.error("Initiating Emergency Liquidation of all assets to Cash...")
        logger.error("="*80)
        
        for tf in ['15m', '5m']:
            portfolio = self.load_portfolio(tf)
            for asset, pos in list(portfolio["positions"].items()):
                try:
                    logger.warning(f"Liquidating {pos['type']} position for {asset} on {tf}...")
                    current_price = self.latest_prices.get(asset, pos["entry_price"])
                    portfolio, _ = await self.close_position(portfolio, asset, current_price, "(Emergency Liquidation)")
                except Exception as e:
                    logger.error(f"Could not liquidate {asset}: {e}")
                    
            portfolio["total_value"] = portfolio["cash"]
            self.save_portfolio(portfolio, tf)
        logger.info("Emergency Liquidation Complete. Shutting down permanently.")
        await self.exchange.close()
        sys.exit(1)

    def construct_state_vector(self, df: pd.DataFrame, current_sentiment: float = 0.5) -> Tuple[List[float], float]:
        current_price = df['close'].iloc[-1]
        volatility = df['close'].pct_change().rolling(24).std().iloc[-1]
        vol_spike = (df['volume'].iloc[-1] / df['volume'].rolling(60).mean().iloc[-1])
        z_score = ((current_price - df['close'].rolling(100).mean().iloc[-1]) / df['close'].rolling(100).std().iloc[-1])
        
        state_vector = [
            1.0, current_sentiment, 0.0, z_score, z_score * 0.9, z_score * 1.1, z_score * 0.8,
            volatility, volatility, volatility, volatility, volatility, volatility,
            vol_spike, vol_spike, vol_spike, vol_spike, vol_spike
        ]
        return [0.0 if np.isnan(x) else float(x) for x in state_vector], float(current_price)

    def log_trade(self, asset: str, price: float, action_str: str, confidence: float, allocation: float, pnl: float = 0.0) -> None:
        trade_data = {
            'timestamp': [pd.Timestamp.now('UTC').isoformat()],
            'asset': [asset],
            'price': [price],
            'action': [action_str],
            'confidence': [f"{confidence:.2f}"],
            'allocation': [f"{allocation*100:.2f}%"],
            'pnl': [f"{pnl:.2f}"]
        }
        pd.DataFrame(trade_data).to_csv(self.log_file, mode='a', header=False, index=False)

    async def close_position(self, portfolio: Dict[str, Any], asset: str, current_price: float, reason: str = "") -> Tuple[Dict[str, Any], bool, float]:
        if asset not in portfolio["positions"]:
            return portfolio, False, 0.0
            
        pos = portfolio["positions"][asset]
        
        try:
            orderbook = await self.exchange.fetch_order_book(asset)
            best_bid = orderbook['bids'][0][0] if len(orderbook['bids']) > 0 else current_price
            best_ask = orderbook['asks'][0][0] if len(orderbook['asks']) > 0 else current_price
            
            if pos["type"] == "LONG":
                logger.info(f"Paper Executing Limit SELL for {pos['amount']} {asset} @ ${best_ask:,.2f}...")
            elif pos["type"] == "SHORT":
                logger.info(f"Paper Executing Limit BUY (Cover SHORT) for {pos['amount']} {asset} @ ${best_bid:,.2f}...")
        except Exception as e:
            logger.error(f"Binance Execution Error (Limit Order): {e}")
            self.error_count += 1
            if self.error_count >= 3:
                await self.emergency_liquidation("3 consecutive Binance API Errors detected.")
            return portfolio, False, 0.0
        
        self.error_count = 0 
        
        if pos["type"] == "LONG":
            sell_value = pos["amount"] * current_price * (1 - self.fee_rate)
            cost_basis = pos["amount"] * pos["entry_price"]
            pnl = sell_value - cost_basis
        else: # SHORT
            buy_cost = pos["amount"] * current_price * (1 + self.fee_rate)
            short_credit = pos["amount"] * pos["entry_price"]
            pnl = short_credit - buy_cost
            
        portfolio["cash"] += pos.get("locked_cash", 0) + pnl 
        portfolio["realized_pnl"] += pnl
        del portfolio["positions"][asset]
        
        logger.info(f"Closed {pos['type']} {asset} @ ${current_price:,.2f} | PNL: ${pnl:,.2f} {reason}")
        return portfolio, True, pnl

    async def open_position(self, portfolio: Dict[str, Any], asset: str, current_price: float, pos_type: str, allocation_pct: float) -> Tuple[Dict[str, Any], bool]:
        invest_amount = portfolio["cash"] * allocation_pct
        
        if invest_amount < 15:
            return portfolio, False 
            
        amount_asset = (invest_amount * (1 - self.fee_rate)) / current_price
        
        try:
            orderbook = await self.exchange.fetch_order_book(asset)
            best_bid = orderbook['bids'][0][0] if len(orderbook['bids']) > 0 else current_price
            best_ask = orderbook['asks'][0][0] if len(orderbook['asks']) > 0 else current_price
            
            if pos_type == "LONG":
                logger.info(f"Paper Executing Limit BUY for {amount_asset} {asset} @ ${best_bid:,.2f}...")
                executed_price = best_bid
            elif pos_type == "SHORT":
                logger.info(f"Paper Executing Limit SELL (SHORT) for {amount_asset} {asset} @ ${best_ask:,.2f}...")
                executed_price = best_ask
        except Exception as e:
            logger.error(f"Binance Execution Error (Limit Order): {e}")
            self.error_count += 1
            if self.error_count >= 3:
                await self.emergency_liquidation("3 consecutive Binance API Errors detected.")
            return portfolio, False
            
        self.error_count = 0 
        
        portfolio["cash"] -= invest_amount
        portfolio["positions"][asset] = {
            "type": pos_type,
            "amount": amount_asset,
            "entry_price": executed_price,
            "locked_cash": invest_amount
        }
        logger.info(f"Opened {pos_type} {asset} @ ${executed_price:,.2f} (Limit Order) | Size: ${invest_amount:,.2f}")
        return portfolio, True

    async def execute_live_trade(self, portfolio: Dict[str, Any], asset: str, current_price: float, action: int, conf: float, allocation_pct: float) -> Dict[str, Any]:
        """
        Executes a real order against the Binance API.
        """
        action_map = {0: "SHORT", 1: "NEUTRAL", 2: "LONG"}
        action_str = action_map.get(action, "UNKNOWN")
        
        try:
            # Sync balance from real exchange
            balance = await self.exchange.fetch_balance()
            usdt_balance = balance['USDT']['free']
            
            # If AI wants to execute, calculate real order size
            if action in [0, 2]:
                invest_amount = usdt_balance * allocation_pct
                if invest_amount < 10.0:
                    logger.warning(f"Trade size too small for {asset}: ${invest_amount:.2f}")
                    return portfolio
                    
                order_qty = invest_amount / current_price
                
                # Simplified real execution logic
                if action == 2: # LONG
                    logger.warning(f"Executing LIVE MARKET BUY for {asset} Size: {order_qty}")
                    order = await self.exchange.create_market_buy_order(asset, order_qty)
                    self.log_trade(asset, current_price, "LONG", conf, allocation_pct)
                    
                elif action == 0: # SHORT
                    logger.warning(f"Executing LIVE MARKET SELL (SHORT) for {asset} Size: {order_qty}")
                    order = await self.exchange.create_market_sell_order(asset, order_qty)
                    self.log_trade(asset, current_price, "SHORT", conf, allocation_pct)
                    
            elif action == 1:
                # Close position on NEUTRAL
                pass # Further implementation required for parsing live open positions
                
        except Exception as e:
            logger.error(f"Live Execution Error on {asset}: {e}")
            
        return portfolio

    async def execute_paper_trade(self, portfolio: Dict[str, Any], asset: str, current_price: float, action: int, conf: float, allocation_pct: float) -> Dict[str, Any]:
        action_map = {0: "SHORT", 1: "NEUTRAL", 2: "LONG"}
        action_str = action_map.get(action, "UNKNOWN")
        
        has_pos = asset in portfolio["positions"]
        trade_executed = False
        
        if action == 2: 
            if has_pos and portfolio["positions"][asset]["type"] == "SHORT":
                portfolio, _, closed_pnl = await self.close_position(portfolio, asset, current_price, "(Flipping Long)")
                self.log_trade(asset, current_price, "EXIT", 1.0, 0.0, closed_pnl)
                portfolio, trade_executed = await self.open_position(portfolio, asset, current_price, "LONG", allocation_pct)
            elif not has_pos:
                portfolio, trade_executed = await self.open_position(portfolio, asset, current_price, "LONG", allocation_pct)
                
        elif action == 0: 
            if has_pos and portfolio["positions"][asset]["type"] == "LONG":
                portfolio, _, closed_pnl = await self.close_position(portfolio, asset, current_price, "(Flipping Short)")
                self.log_trade(asset, current_price, "EXIT", 1.0, 0.0, closed_pnl)
                portfolio, trade_executed = await self.open_position(portfolio, asset, current_price, "SHORT", allocation_pct)
            elif not has_pos:
                portfolio, trade_executed = await self.open_position(portfolio, asset, current_price, "SHORT", allocation_pct)
                
        elif action == 1: 
            if has_pos:
                portfolio, trade_executed, closed_pnl = await self.close_position(portfolio, asset, current_price, "(Neutral Signal)")
                if trade_executed:
                    self.log_trade(asset, current_price, "EXIT", 1.0, 0.0, closed_pnl)
                    trade_executed = False # Reset so we don't double log below as NEUTRAL

        total_val = portfolio["cash"]
        for p_asset, p_data in portfolio["positions"].items():
            pos_price = self.latest_prices.get(p_asset, p_data["entry_price"])
            total_val += p_data.get("locked_cash", 0)
            if p_data["type"] == "LONG":
                total_val += (pos_price - p_data["entry_price"]) * p_data["amount"]
            else:
                total_val += (p_data["entry_price"] - pos_price) * p_data["amount"]
                
        portfolio["total_value"] = total_val
        
        if portfolio["total_value"] < (self.starting_cash * self.max_drawdown):
            await self.emergency_liquidation(f"Portfolio Value dropped below max drawdown! Current: ${portfolio['total_value']:,.2f}")
        
        if trade_executed:
            self.log_trade(asset, current_price, action_str, conf, allocation_pct)
            
        return portfolio

    async def check_stop_loss_take_profit(self, portfolio: Dict[str, Any], asset: str, current_price: float, timeframe: str) -> Dict[str, Any]:
        if asset not in portfolio["positions"]:
            return portfolio
            
        pos = portfolio["positions"][asset]
        entry = pos["entry_price"]
        
        if pos["type"] == "LONG":
            pct_change = (current_price - entry) / entry
        else: # SHORT
            pct_change = (entry - current_price) / entry
            
        tp_target = 0.01 if timeframe == '5m' else 0.02
        sl_target = -0.005 if timeframe == '5m' else -0.01
            
        if pct_change >= tp_target: 
            portfolio, _, pnl = await self.close_position(portfolio, asset, current_price, f"(Take-Profit Hit on {timeframe}!)")
            self.log_trade(asset, current_price, "TAKE_PROFIT", 1.0, 0.0, pnl)
        elif pct_change <= sl_target: 
            portfolio, _, pnl = await self.close_position(portfolio, asset, current_price, f"(Stop-Loss Hit on {timeframe}!)")
            self.log_trade(asset, current_price, "STOP_LOSS", 1.0, 0.0, pnl)
            
        return portfolio

    async def watch_asset_timeframe(self, asset: str, timeframe: str, brain: MetaAgent) -> None:
        logger.info(f"Initializing WebSocket Tunnel for {asset} on {timeframe}...")
        
        try:
            history = await self.exchange.fetch_ohlcv(asset, timeframe, limit=200)
            df = pd.DataFrame(history, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        except Exception as e:
            logger.error(f"Failed to initialize history for {asset} on {timeframe}: {e}")
            return
            
        logger.info(f"{asset} Context Loaded ({timeframe}). Awaiting Live WebSocket Ticks...")
        
        while not self.kill_switch_activated:
            try:
                candles = await self.exchange.watch_ohlcv(asset, timeframe)
                latest_candle = candles[-1] 
                
                timestamp = pd.to_datetime(latest_candle[0], unit='ms')
                if df.iloc[-1]['timestamp'] == timestamp:
                    df.iloc[-1] = [timestamp] + latest_candle[1:]
                else:
                    df.loc[len(df)] = [timestamp] + latest_candle[1:]
                    
                current_price = latest_candle[4]
                self.latest_prices[asset] = current_price
                
                portfolio = self.load_portfolio(timeframe)
                portfolio = await self.check_stop_loss_take_profit(portfolio, asset, current_price, timeframe)
                
                current_time = time.time()
                if asset not in self.last_news_time or (current_time - self.last_news_time[asset]) > self.news_interval:
                    raw_news = fetch_news._run(asset.split('/')[0])
                    sentiment_score = self.sentiment_agent.analyze(raw_news)
                    self.news_cache[asset] = sentiment_score
                    self.last_news_time[asset] = current_time
                else:
                    sentiment_score = self.news_cache[asset]
                    
                # Fetch Level-2 Order Book Data
                try:
                    orderbook = await self.exchange.watch_order_book(asset)
                    bids = sum([b[1] for b in orderbook['bids'][:10]])
                    asks = sum([a[1] for a in orderbook['asks'][:10]])
                    order_book_imbalance = (bids - asks) / (bids + asks) if (bids + asks) > 0 else 0.0
                except Exception as e:
                    logger.warning(f"L2 Orderbook fetch failed for {asset}: {e}")
                    order_book_imbalance = 0.0
                    
                state_vector, _ = self.construct_state_vector(df, current_sentiment=sentiment_score)
                # Append L2 Order Book Imbalance to make it 19-Dimensional
                state_vector.append(float(order_book_imbalance))
                
                # Sequence Memory Buffer for Transformer
                if not hasattr(self, 'sequence_buffers'):
                    self.sequence_buffers = {}
                if f"{asset}_{timeframe}" not in self.sequence_buffers:
                    self.sequence_buffers[f"{asset}_{timeframe}"] = deque(maxlen=10)
                    
                self.sequence_buffers[f"{asset}_{timeframe}"].append(state_vector)
                
                # We need a full 10-candle sequence before the Transformer can make a decision
                if len(self.sequence_buffers[f"{asset}_{timeframe}"]) < 10:
                    logger.info(f"{asset} ({timeframe}): Buffering sequence ({len(self.sequence_buffers[f'{asset}_{timeframe}'])}/10)...")
                    continue
                    
                with torch.no_grad():
                    sequence_list = list(self.sequence_buffers[f"{asset}_{timeframe}"])
                    action = brain.get_action(sequence_list, epsilon=0.0)
                    action_str = {0: "SHORT", 1: "HOLD", 2: "LONG"}.get(action, "UNKNOWN")
                    logger.info(f"AI Decision for {asset} ({timeframe}): {action_str} (Action Code: {action})")
                
                conf = 1.0 if action in [0, 2] else 0.5
                allocation = self.risk_manager.calculate_position_size(conf, 0.02, current_price)
                
                if self.trading_mode == 'LIVE':
                    portfolio = await self.execute_live_trade(portfolio, asset, current_price, action, conf, allocation)
                else:
                    portfolio = await self.execute_paper_trade(portfolio, asset, current_price, action, conf, allocation)
                    
                self.save_portfolio(portfolio, timeframe)
                
            except ccxt.RateLimitExceeded as e:
                logger.error(f"[CIRCUIT BREAKER] 429 Too Many Requests on {asset}: {e}")
                await self.emergency_liquidation("Exchange API Rate Limit Exceeded (429). Triggering Safe Mode.")
            except ccxt.NetworkError as e:
                self.error_count += 1
                logger.error(f"[CIRCUIT BREAKER] Network Error on {asset}: {e}")
                if self.error_count >= 3:
                    await self.emergency_liquidation("3 consecutive Binance Network Errors detected. Connection dropped.")
                await asyncio.sleep(5) 
            except Exception as e:
                self.error_count += 1
                logger.error(f"WebSocket General Error on {asset}: {e}")
                if self.error_count >= 3:
                    await self.emergency_liquidation("3 consecutive unknown errors detected.")
                await asyncio.sleep(5) 

    async def run_loop(self) -> None:
        logger.info("Booting Dual-Brain Institutional WebSocket Architecture...")
        tasks = []
        for asset in self.assets:
            tasks.append(self.watch_asset_timeframe(asset, '15m', self.swing_brain))
            tasks.append(self.watch_asset_timeframe(asset, '5m', self.intraday_brain))
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    trader = AsyncPaperTrader()
    try:
        asyncio.run(trader.run_loop())
    except KeyboardInterrupt:
        logger.info("Shutting down Trading Engine...")
    finally:
        # Gracefully close CCXT to prevent aiohttp unclosed session errors
        async def cleanup():
            await trader.exchange.close()
        asyncio.run(cleanup())
