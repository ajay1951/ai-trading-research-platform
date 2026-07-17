import os
import sys
import asyncio
import time
import ccxt.pro as ccxtpro
import pandas as pd
import numpy as np
import torch
import json
import redis
import yaml
import logging
from typing import List, Dict, Any, Tuple
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
        self.model_path: str = self.config['mlops']['model_path']
        
        logger.info("Connecting to Binance Futures Testnet (WebSockets)...")
        self.exchange = ccxtpro.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        # Binance Sandbox is deprecated for futures. We use Live market data but paper trade locally.
        
        logger.info("Loading Universal AI Brain...")
        self.brain = MetaAgent(input_dim=18, buffer_size=1000, batch_size=64)
        
        full_model_path = os.path.join(os.path.dirname(__file__), '..', self.model_path)
        if os.path.exists(full_model_path):
            self.brain.q_network.load_state_dict(torch.load(full_model_path, map_location=torch.device('cpu'), weights_only=True))
            self.brain.q_network.eval()
            logger.info("Neural Network Weights Loaded Successfully.")
        else:
            logger.warning(f"{self.model_path} not found. AI will trade randomly until trained.")
            
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
        
        self._init_files()

    def _init_files(self) -> None:
        if not os.path.exists(self.log_file):
            pd.DataFrame(columns=['timestamp', 'asset', 'price', 'action', 'confidence', 'allocation']).to_csv(self.log_file, index=False)
            
        needs_reset = True
        if self.redis_client.exists("live_portfolio"):
            try:
                current_port = json.loads(self.redis_client.get("live_portfolio"))
                if current_port.get("total_value", 0) >= (self.starting_cash * self.max_drawdown):
                    needs_reset = False
            except Exception:
                pass
                
        if needs_reset:
            logger.info("Initializing or Resetting Portfolio (Old portfolio was below Max Drawdown)...")
            initial_portfolio = {
                "cash": self.starting_cash,
                "positions": {}, 
                "realized_pnl": 0.0,
                "total_value": self.starting_cash
            }
            self.save_portfolio(initial_portfolio)

    def load_portfolio(self) -> Dict[str, Any]:
        data = self.redis_client.get("live_portfolio")
        if data:
            return json.loads(str(data))
        return {"cash": self.starting_cash, "positions": {}, "realized_pnl": 0.0, "total_value": self.starting_cash}

    def save_portfolio(self, portfolio: Dict[str, Any]) -> None:
        self.redis_client.set("live_portfolio", json.dumps(portfolio))

    async def emergency_liquidation(self, reason: str) -> None:
        if self.kill_switch_activated: return
        self.kill_switch_activated = True
        
        logger.error("="*80)
        logger.error("!!! CRITICAL ALERT: CIRCUIT BREAKER TRIGGERED !!!")
        logger.error(f"Reason: {reason}")
        logger.error("Initiating Emergency Liquidation of all assets to Cash...")
        logger.error("="*80)
        
        portfolio = self.load_portfolio()
        for asset, pos in list(portfolio["positions"].items()):
            try:
                logger.warning(f"Liquidating {pos['type']} position for {asset}...")
                if pos["type"] == "LONG":
                    pass # Paper trade: no real API call
                else:
                    pass # Paper trade: no real API call
            except Exception as e:
                logger.error(f"Could not liquidate {asset}: {e}")
                
        portfolio["positions"] = {}
        self.save_portfolio(portfolio)
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

    def log_trade(self, asset: str, price: float, action_str: str, confidence: float, allocation: float) -> None:
        trade_data = {
            'timestamp': [pd.Timestamp.now('UTC').isoformat()],
            'asset': [asset],
            'price': [price],
            'action': [action_str],
            'confidence': [f"{confidence:.2f}"],
            'allocation': [f"{allocation*100:.2f}%"]
        }
        pd.DataFrame(trade_data).to_csv(self.log_file, mode='a', header=False, index=False)

    async def close_position(self, portfolio: Dict[str, Any], asset: str, current_price: float, reason: str = "") -> Tuple[Dict[str, Any], bool]:
        if asset not in portfolio["positions"]:
            return portfolio, False
            
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
            return portfolio, False
        
        self.error_count = 0 
        
        if pos["type"] == "LONG":
            sell_value = pos["amount"] * current_price * (1 - self.fee_rate)
            cost_basis = pos["amount"] * pos["entry_price"]
            pnl = sell_value - cost_basis
        else: # SHORT
            buy_cost = pos["amount"] * current_price * (1 + self.fee_rate)
            short_credit = pos["amount"] * pos["entry_price"]
            pnl = short_credit - buy_cost
            
        portfolio["cash"] += pnl 
        portfolio["realized_pnl"] += pnl
        del portfolio["positions"][asset]
        
        logger.info(f"Closed {pos['type']} {asset} @ ${current_price:,.2f} | PNL: ${pnl:,.2f} {reason}")
        return portfolio, True

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

    async def execute_paper_trade(self, portfolio: Dict[str, Any], asset: str, current_price: float, action: int, conf: float, allocation_pct: float) -> Dict[str, Any]:
        action_map = {0: "SHORT", 1: "NEUTRAL", 2: "LONG"}
        action_str = action_map.get(action, "UNKNOWN")
        
        has_pos = asset in portfolio["positions"]
        trade_executed = False
        
        if action == 2: 
            if has_pos and portfolio["positions"][asset]["type"] == "SHORT":
                portfolio, _ = await self.close_position(portfolio, asset, current_price, "(Flipping Long)")
                portfolio, trade_executed = await self.open_position(portfolio, asset, current_price, "LONG", allocation_pct)
            elif not has_pos:
                portfolio, trade_executed = await self.open_position(portfolio, asset, current_price, "LONG", allocation_pct)
                
        elif action == 0: 
            if has_pos and portfolio["positions"][asset]["type"] == "LONG":
                portfolio, _ = await self.close_position(portfolio, asset, current_price, "(Flipping Short)")
                portfolio, trade_executed = await self.open_position(portfolio, asset, current_price, "SHORT", allocation_pct)
            elif not has_pos:
                portfolio, trade_executed = await self.open_position(portfolio, asset, current_price, "SHORT", allocation_pct)
                
        elif action == 1: 
            if has_pos:
                portfolio, trade_executed = await self.close_position(portfolio, asset, current_price, "(Neutral Signal)")

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

    async def check_stop_loss_take_profit(self, portfolio: Dict[str, Any], asset: str, current_price: float) -> Dict[str, Any]:
        if asset not in portfolio["positions"]:
            return portfolio
            
        pos = portfolio["positions"][asset]
        entry = pos["entry_price"]
        
        if pos["type"] == "LONG":
            pct_change = (current_price - entry) / entry
        else: # SHORT
            pct_change = (entry - current_price) / entry
            
        if pct_change >= 0.02: 
            portfolio, _ = await self.close_position(portfolio, asset, current_price, "(Take-Profit Hit!)")
            self.log_trade(asset, current_price, "TAKE_PROFIT", 1.0, 0.0)
        elif pct_change <= -0.01: 
            portfolio, _ = await self.close_position(portfolio, asset, current_price, "(Stop-Loss Hit!)")
            self.log_trade(asset, current_price, "STOP_LOSS", 1.0, 0.0)
            
        return portfolio

    async def watch_asset(self, asset: str) -> None:
        logger.info(f"Initializing WebSocket Tunnel for {asset}...")
        
        try:
            history = await self.exchange.fetch_ohlcv(asset, '15m', limit=200)
            df = pd.DataFrame(history, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        except Exception as e:
            logger.error(f"Failed to initialize history for {asset}: {e}")
            return
            
        logger.info(f"{asset} Context Loaded. Awaiting Live WebSocket Ticks...")
        
        while not self.kill_switch_activated:
            try:
                candles = await self.exchange.watch_ohlcv(asset, '15m')
                latest_candle = candles[-1] 
                
                timestamp = pd.to_datetime(latest_candle[0], unit='ms')
                if df.iloc[-1]['timestamp'] == timestamp:
                    df.iloc[-1] = [timestamp] + latest_candle[1:]
                else:
                    df.loc[len(df)] = [timestamp] + latest_candle[1:]
                    
                current_price = latest_candle[4]
                self.latest_prices[asset] = current_price
                
                portfolio = self.load_portfolio()
                portfolio = await self.check_stop_loss_take_profit(portfolio, asset, current_price)
                
                current_time = time.time()
                if asset not in self.last_news_time or (current_time - self.last_news_time[asset]) > self.news_interval:
                    logger.info(f"Scraping latest headlines for {asset}...")
                    raw_news = fetch_news._run(asset.split('/')[0])
                    sentiment_score = self.sentiment_agent.analyze(raw_news)
                    self.news_cache[asset] = sentiment_score
                    self.last_news_time[asset] = current_time
                else:
                    sentiment_score = self.news_cache[asset]
                    
                state_vector, _ = self.construct_state_vector(df, current_sentiment=sentiment_score)
                with torch.no_grad():
                    action = self.brain.get_action(state_vector, epsilon=0.0)
                
                conf = 1.0 if action in [0, 2] else 0.5
                allocation = self.risk_manager.calculate_position_size(conf, 0.02, current_price)
                
                portfolio = await self.execute_paper_trade(portfolio, asset, current_price, action, conf, allocation)
                self.save_portfolio(portfolio)
                
            except Exception as e:
                self.error_count += 1
                logger.error(f"WebSocket Error on {asset}: {e}")
                if self.error_count >= 3:
                    await self.emergency_liquidation("3 consecutive Binance WebSocket Errors detected.")
                await asyncio.sleep(5) 

    async def run_loop(self) -> None:
        logger.info("Booting Institutional WebSocket Architecture...")
        tasks = [self.watch_asset(asset) for asset in self.assets]
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
