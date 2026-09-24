import os
import sys
import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        import aiohttp.resolver
        aiohttp.resolver.AsyncResolver = aiohttp.resolver.ThreadedResolver
    except ImportError:
        pass

import time
import ccxt
import ccxt.pro as ccxtpro
import pandas as pd
import numpy as np
import json
import aiofiles
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

import sys
import torch
import torch.nn as nn

# Re-define the LSTM model to avoid circular imports from benchmark script
class CryptoRTXLSTM(nn.Module):
    def __init__(self, input_dim, hidden_dim=64, num_layers=2):
        super(CryptoRTXLSTM, self).__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.3)
        self.fc1 = nn.Linear(hidden_dim, 32)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.2)
        self.fc2 = nn.Linear(32, 2)
        
    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        last_out = lstm_out[:, -1, :]
        out = self.fc1(last_out)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        return out

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))
from risk_agent import RiskAgent
from regime_agent import RegimeAgent
import joblib

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tools'))
from news_tools import fetch_news

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backtesting'))
from quant_features import QuantFeatureEngineer

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
        
        self.leverage: float = 3.0 # Set Institutional 3x Leverage
        self.trading_mode: str = os.getenv('TRADING_MODE', 'PAPER').upper()
        
        logger.info(f"Booting Trading Engine in {self.trading_mode} Mode...")
        
        exchange_config = {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap'
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
            
        self.exchange = ccxtpro.binanceusdm(exchange_config)
        
        logger.info("Loading PyTorch LSTM FP16 Production Model...")
        scaler_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'scaler.pkl')
        if os.path.exists(scaler_path):
            self.scaler = joblib.load(scaler_path)
        else:
            self.scaler = None
            
        prod_model_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'universal_crypto_rtx_lstm.pth')
        if os.path.exists(prod_model_path):
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            checkpoint = torch.load(prod_model_path, map_location=self.device)
            # Dynamically set input_dim based on the saved rich checkpoint features
            saved_features = checkpoint.get('features', [])
            input_dim = len(saved_features) if len(saved_features) > 0 else 24
            
            self.model = CryptoRTXLSTM(input_dim=input_dim).to(self.device)
            self.model.load_state_dict(checkpoint['model_state_dict'])
            # We no longer strictly cast to .half() here, AMP handles it dynamically
            self.model.eval()
            win_rate = checkpoint.get('backtest_performance', {}).get('win_rate', 0.0) * 100
            logger.info(f"PyTorch LSTM Rich Checkpoint Loaded (Backtest Win Rate: {win_rate:.1f}%).")
        else:
            logger.warning(f"{prod_model_path} not found. Trading will be disabled.")
            self.model = None
            
        self.position_locks = {}
            
        self.risk_manager = RiskAgent()
        self.regime_agent = RegimeAgent()
        
        self.log_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'live_trades.csv')
        self.state_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolio_state.json')
        
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
        
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    all_portfolios = json.load(f)
                if timeframe in all_portfolios:
                    current_port = all_portfolios[timeframe]
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
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    all_portfolios = json.load(f)
                if timeframe in all_portfolios:
                    return all_portfolios[timeframe]
            except Exception:
                pass
        return {"cash": self.starting_cash / 2, "positions": {}, "realized_pnl": 0.0, "total_value": self.starting_cash / 2}

    def save_portfolio(self, portfolio: Dict[str, Any], timeframe: str) -> None:
        all_portfolios = {}
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    all_portfolios = json.load(f)
            except Exception:
                pass
                
        all_portfolios[timeframe] = portfolio
        with open(self.state_file, 'w') as f:
            json.dump(all_portfolios, f, indent=4)

    async def async_save_portfolio(self, portfolio: Dict[str, Any], timeframe: str) -> None:
        all_portfolios = {}
        if os.path.exists(self.state_file):
            try:
                async with aiofiles.open(self.state_file, 'r') as f:
                    content = await f.read()
                    all_portfolios = json.loads(content)
            except Exception:
                pass
                
        all_portfolios[timeframe] = portfolio
        async with aiofiles.open(self.state_file, 'w') as f:
            await f.write(json.dumps(all_portfolios, indent=4))

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
            await self.async_save_portfolio(portfolio, tf)
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
            cost_basis = pos["notional_size"]
            pnl = sell_value - cost_basis
        else: # SHORT
            buy_cost = pos["amount"] * current_price * (1 + self.fee_rate)
            short_credit = pos["notional_size"]
            pnl = short_credit - buy_cost
            
        portfolio["cash"] += pos.get("locked_cash", 0) + pnl 
        portfolio["realized_pnl"] += pnl
        del portfolio["positions"][asset]
        
        logger.info(f"Closed {pos['type']} {asset} @ ${current_price:,.2f} | PNL: ${pnl:,.2f} {reason}")
        return portfolio, True, pnl

    async def open_position(self, portfolio: Dict[str, Any], asset: str, current_price: float, pos_type: str, allocation_pct: float) -> Tuple[Dict[str, Any], bool]:
        margin_used = portfolio["cash"] * allocation_pct
        notional_amount = margin_used * self.leverage
        
        if notional_amount < 15:
            return portfolio, False 
            
        amount_asset = (notional_amount * (1 - self.fee_rate)) / current_price
        
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
        
        portfolio["cash"] -= margin_used
        portfolio["positions"][asset] = {
            "type": pos_type,
            "amount": amount_asset,
            "entry_price": executed_price,
            "locked_cash": margin_used,
            "notional_size": notional_amount
        }
        logger.info(f"Opened {pos_type} {asset} @ ${executed_price:,.2f} | Margin: ${margin_used:,.2f} | Size (x{self.leverage}): ${notional_amount:,.2f}")
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
            
            # Ensure Leverage is set on Binance before ordering
            try:
                await self.exchange.set_leverage(int(self.leverage), asset)
            except Exception as e:
                logger.debug(f"Leverage may already be set for {asset}: {e}")
            
            # If AI wants to execute, calculate real order size using Notional Leverage
            if action in [0, 2]:
                notional_amount = usdt_balance * allocation_pct * self.leverage
                if notional_amount < 10.0:
                    logger.warning(f"Trade size too small for {asset}: ${notional_amount:.2f}")
                    return portfolio
                    
                order_qty = notional_amount / current_price
                
                # Fetch order book for Maker pricing
                orderbook = await self.exchange.fetch_order_book(asset)
                best_bid = orderbook['bids'][0][0] if len(orderbook['bids']) > 0 else current_price
                best_ask = orderbook['asks'][0][0] if len(orderbook['asks']) > 0 else current_price
                
                # Simplified real execution logic
                if action == 2: # LONG
                    limit_price = best_bid
                    logger.warning(f"Executing LIVE LIMIT BUY for {asset} Notional Size: {order_qty} @ {limit_price} (x{self.leverage})")
                    order = await self.exchange.create_limit_buy_order(asset, order_qty, limit_price)
                    self.log_trade(asset, limit_price, "LONG", conf, allocation_pct)
                    
                elif action == 0: # SHORT
                    limit_price = best_ask
                    logger.warning(f"Executing LIVE LIMIT SELL (SHORT) for {asset} Notional Size: {order_qty} @ {limit_price} (x{self.leverage})")
                    order = await self.exchange.create_limit_sell_order(asset, order_qty, limit_price)
                    self.log_trade(asset, limit_price, "SHORT", conf, allocation_pct)
                    
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
        
        if portfolio["total_value"] < ((self.starting_cash / 2) * self.max_drawdown):
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

    async def watch_asset_timeframe(self, asset: str, timeframe: str, brain=None) -> None:
        logger.info(f"Initializing WebSocket Tunnel for {asset} on {timeframe}...")
        
        try:
            import ccxt
            sync_exchange = ccxt.binanceusdm({'enableRateLimit': True})
            history = sync_exchange.fetch_ohlcv(asset, timeframe, limit=200)
            df = pd.DataFrame(history, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        except Exception as e:
            logger.error(f"Failed to initialize history for {asset} on {timeframe}: {e}")
            return
            
        logger.info(f"{asset} Context Loaded ({timeframe}). Awaiting Live WebSocket Ticks...")
        
        sequence_buffer = deque(maxlen=50)
        
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
                
                # Fetch Level-2 Order Book Data
                try:
                    orderbook = await self.exchange.watch_order_book(asset)
                    bids = sum([b[1] for b in orderbook['bids'][:10]])
                    asks = sum([a[1] for a in orderbook['asks'][:10]])
                    order_book_imbalance = (bids - asks) / (bids + asks) if (bids + asks) > 0 else 0.0
                except Exception as e:
                    logger.warning(f"L2 Orderbook fetch failed for {asset}: {e}")
                    order_book_imbalance = 0.0
                    
                # Regime Classification (Daily context simulated from DF)
                current_regime = self.regime_agent.classify(df)
                if current_regime == "RANGING":
                    logger.info(f"{asset}: Regime is RANGING. Halting trades.")
                    continue
                    
                # We dynamically construct the exact 24-dim state vector here!
                base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
                asset_clean = asset.replace(':', '')
                # Fast in-memory feature engineering on the live rolling DF
                engineer = QuantFeatureEngineer(asset_name=asset_clean, data_dir=base_dir, base_timeframe=timeframe)
                engineer.df = df.copy() # Override disk DF with live CCXT DF
                engineer.calculate_macro_trend()
                engineer.calculate_base_trend()
                engineer.calculate_intermediate_volatility()
                engineer.calculate_micro_structure()
                engineer.calculate_advanced_ohlcv()
                engineer.merge_derivatives()
                engineer.merge_macro_economic_data()
                
                live_features = engineer.get_features()
                if live_features.empty:
                    continue
                    
                latest_row = live_features.iloc[-1].to_dict()
                
                # Fill missing macro features with 0.0 to match the 24-dim shape safely without disk IO
                features_list = [
                    '1mo_z_score', '1w_z_score', '3d_z_score', '1d_z_score', 
                    '12h_volatility', '8h_volatility', '6h_volatility', '4h_volatility', '2h_volatility', '1h_volatility', 
                    '30m_volume_spike', '15m_volume_spike', '5m_volume_spike', '3m_volume_spike', '1m_volume_spike', 
                    'ATR_14', 'log_return', 'RSI_14', 'MACD', 'MACD_hist', 'BB_Width',
                    'funding_rate', 'open_interest', 'sentiment_score', 'DXY', 'SPX', 'TNX'
                ]
                
                state_vector = []
                for f in features_list:
                    val = latest_row.get(f, 0.0)
                    if pd.isna(val): val = 0.0
                    state_vector.append(float(val))
                
                # Append to LSTM sequence buffer
                sequence_buffer.append(state_vector)
                if len(sequence_buffer) < 50:
                    continue # Wait for the 50-candle sequence to fill
                
                probs = 0.5
                if self.model is not None and self.scaler is not None:
                    # Scale the entire 50-candle sequence
                    scaled_sequence = self.scaler.transform(list(sequence_buffer))
                    # Keep tensor in FP32, let AMP handle downcasting
                    seq_tensor = torch.tensor(scaled_sequence, dtype=torch.float32).unsqueeze(0).to(self.device)
                    
                    with torch.no_grad():
                        with torch.cuda.amp.autocast():
                            logits = self.model(seq_tensor)
                        probs = torch.softmax(logits, dim=1)[:, 1].item()
                        
                    # Enforce Institutional Confidence Threshold (72%)
                    action = 2 if probs >= 0.72 else 1 
                    action_str = {0: "SHORT", 1: "HOLD", 2: "LONG"}.get(action, "UNKNOWN")
                    if action == 2:
                        logger.info(f"LSTM Decision for {asset} ({timeframe}): {action_str} ({probs*100:.1f}%)")
                else:
                    action = 1
                
                conf = probs
                current_atr = latest_row.get('ATR_14', current_price * 0.02)
                
                # Volatility Filter
                predicted_slippage = 0.001 + ((current_atr / current_price) * 0.5)
                if predicted_slippage > 0.004 and action != 1:
                    logger.warning(f"Trade Skipped: {asset} is too volatile (Slippage: {predicted_slippage*100:.2f}%)")
                    action = 1
                
                allocation = self.risk_manager.calculate_position_size(conf, current_atr, current_price, reward_risk_ratio=2.0)
                
                # Concurrent Position Lock: Prevents rapid duplicate executions from serially correlated signals
                async with self.position_locks[asset]:
                    if self.trading_mode == 'LIVE':
                        portfolio = await self.execute_live_trade(portfolio, asset, current_price, action, conf, allocation)
                    else:
                        portfolio = await self.execute_paper_trade(portfolio, asset, current_price, action, conf, allocation)
                        
                    await self.async_save_portfolio(portfolio, timeframe)
                
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
        logger.info("Booting PyTorch LSTM FP16 WebSocket Architecture...")
        
        # Initialize Concurrent Position Locks
        for asset in self.assets:
            swap_symbol = f"{asset}:USDT"
            self.position_locks[swap_symbol] = asyncio.Lock()
            
        tasks = []
        for asset in self.assets:
            swap_symbol = f"{asset}:USDT"
            tasks.append(self.watch_asset_timeframe(swap_symbol, '5m', None))
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
