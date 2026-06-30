import os
import sys
import time
import ccxt
import pandas as pd
import numpy as np
import torch
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))
from meta_agent import MetaAgent
from risk_agent import RiskAgent

class PaperTrader:
    def __init__(self, assets=["BTC/USDT"], model_path="universal_meta_agent.pth"):
        self.assets = assets
        
        print("[+] Connecting to Binance Futures Testnet...")
        self.exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET_KEY'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'  # Enable Futures for Bi-Directional LONG/SHORT trading
            }
        })
        self.exchange.set_sandbox_mode(True)
        
        self.model_path = model_path
        
        print("[+] Loading Universal AI Brain...")
        self.brain = MetaAgent(input_dim=18, buffer_size=1000, batch_size=64)
        
        full_model_path = os.path.join(os.path.dirname(__file__), '..', model_path)
        if os.path.exists(full_model_path):
            self.brain.q_network.load_state_dict(torch.load(full_model_path, map_location=torch.device('cpu'), weights_only=True))
            self.brain.q_network.eval()
            print("[OK] Neural Network Weights Loaded Successfully.")
        else:
            print("[!] Warning: universal_meta_agent.pth not found.")
            
        self.risk_manager = RiskAgent()
        
        self.log_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'live_trades.csv')
        self.portfolio_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolio.json')
        self._init_files()

    def _init_files(self):
        if not os.path.exists(self.log_file):
            pd.DataFrame(columns=['timestamp', 'asset', 'price', 'action', 'confidence', 'allocation']).to_csv(self.log_file, index=False)
            
        if not os.path.exists(self.portfolio_file):
            initial_portfolio = {
                "cash": 10000.00,
                "positions": {}, # {"BTC/USDT": {"type": "LONG", "amount": 0.1, "entry_price": 50000}}
                "realized_pnl": 0.0,
                "total_value": 10000.00
            }
            with open(self.portfolio_file, 'w') as f:
                json.dump(initial_portfolio, f, indent=4)

    def load_portfolio(self):
        with open(self.portfolio_file, 'r') as f:
            return json.load(f)

    def save_portfolio(self, portfolio):
        with open(self.portfolio_file, 'w') as f:
            json.dump(portfolio, f, indent=4)

    def fetch_live_data(self, asset):
        try:
            # Shifted to 15m timeframe for Professional Setup
            ohlcv = self.exchange.fetch_ohlcv(asset, timeframe='15m', limit=200)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"[!] Error fetching {asset}: {e}")
            return None

    def construct_state_vector(self, df):
        current_price = df['close'].iloc[-1]
        volatility = df['close'].pct_change().rolling(24).std().iloc[-1]
        vol_spike = (df['volume'].iloc[-1] / df['volume'].rolling(60).mean().iloc[-1])
        z_score = ((current_price - df['close'].rolling(100).mean().iloc[-1]) / df['close'].rolling(100).std().iloc[-1])
        
        state_vector = [
            1.0, 0.5, 0.0, z_score, z_score * 0.9, z_score * 1.1, z_score * 0.8,
            volatility, volatility, volatility, volatility, volatility, volatility,
            vol_spike, vol_spike, vol_spike, vol_spike, vol_spike
        ]
        return [0.0 if np.isnan(x) else x for x in state_vector], current_price

    def log_trade(self, asset, price, action_str, confidence, allocation):
        trade_data = {
            'timestamp': [pd.Timestamp.now('UTC').isoformat()],
            'asset': [asset],
            'price': [price],
            'action': [action_str],
            'confidence': [f"{confidence:.2f}"],
            'allocation': [f"{allocation*100:.2f}%"]
        }
        pd.DataFrame(trade_data).to_csv(self.log_file, mode='a', header=False, index=False)

    def close_position(self, portfolio, asset, current_price, reason=""):
        if asset not in portfolio["positions"]:
            return portfolio, False
            
        pos = portfolio["positions"][asset]
        fee_rate = 0.001
        
        try:
            symbol = asset
            amount = pos["amount"]
            if pos["type"] == "LONG":
                print(f"[BINANCE FUTURES] Executing Market SELL for {amount} {symbol}...")
                self.exchange.create_market_sell_order(symbol, amount)
            elif pos["type"] == "SHORT":
                print(f"[BINANCE FUTURES] Executing Market BUY (Cover SHORT) for {amount} {symbol}...")
                self.exchange.create_market_buy_order(symbol, amount)
        except Exception as e:
            print(f"[!] Binance Execution Error: {e}")
            return portfolio, False
        
        if pos["type"] == "LONG":
            sell_value = pos["amount"] * current_price * (1 - fee_rate)
            cost_basis = pos["amount"] * pos["entry_price"]
            pnl = sell_value - cost_basis
        else: # SHORT
            buy_cost = pos["amount"] * current_price * (1 + fee_rate)
            short_credit = pos["amount"] * pos["entry_price"]
            pnl = short_credit - buy_cost
            
        portfolio["cash"] += pnl 
        portfolio["realized_pnl"] += pnl
        del portfolio["positions"][asset]
        
        print(f"  => [CLOSE {pos['type']}] {asset} @ ${current_price:,.2f} | PNL: ${pnl:,.2f} {reason}")
        return portfolio, True

    def open_position(self, portfolio, asset, current_price, pos_type, allocation_pct):
        fee_rate = 0.001
        
        try:
            bal = self.exchange.fetch_balance()
            real_cash = bal['free'].get('USDT', portfolio["cash"])
            portfolio["cash"] = real_cash
        except Exception as e:
            pass
            
        invest_amount = portfolio["cash"] * allocation_pct
        
        if invest_amount < 15:
            return portfolio, False # Min trade size
            
        amount_asset = (invest_amount * (1 - fee_rate)) / current_price
        
        try:
            symbol = asset
            if pos_type == "LONG":
                print(f"[BINANCE FUTURES] Executing Market BUY for {amount_asset} {symbol}...")
                self.exchange.create_market_buy_order(symbol, amount_asset)
            elif pos_type == "SHORT":
                print(f"[BINANCE FUTURES] Executing Market SELL (SHORT) for {amount_asset} {symbol}...")
                self.exchange.create_market_sell_order(symbol, amount_asset)
        except Exception as e:
            print(f"[!] Binance Execution Error: {e}")
            return portfolio, False
        
        portfolio["cash"] -= invest_amount
        portfolio["positions"][asset] = {
            "type": pos_type,
            "amount": amount_asset,
            "entry_price": current_price,
            "locked_cash": invest_amount
        }
        print(f"  => [OPEN {pos_type}] {asset} @ ${current_price:,.2f} | Size: ${invest_amount:,.2f}")
        return portfolio, True

    def execute_paper_trade(self, portfolio, asset, current_price, action, conf, allocation_pct):
        action_map = {0: "SHORT", 1: "NEUTRAL", 2: "LONG"}
        action_str = action_map.get(action, "UNKNOWN")
        
        has_pos = asset in portfolio["positions"]
        trade_executed = False
        
        if action == 2: # AI wants to be LONG
            if has_pos and portfolio["positions"][asset]["type"] == "SHORT":
                portfolio, _ = self.close_position(portfolio, asset, current_price, "(Flipping Long)")
                portfolio, trade_executed = self.open_position(portfolio, asset, current_price, "LONG", allocation_pct)
            elif not has_pos:
                portfolio, trade_executed = self.open_position(portfolio, asset, current_price, "LONG", allocation_pct)
                
        elif action == 0: # AI wants to be SHORT
            if has_pos and portfolio["positions"][asset]["type"] == "LONG":
                portfolio, _ = self.close_position(portfolio, asset, current_price, "(Flipping Short)")
                portfolio, trade_executed = self.open_position(portfolio, asset, current_price, "SHORT", allocation_pct)
            elif not has_pos:
                portfolio, trade_executed = self.open_position(portfolio, asset, current_price, "SHORT", allocation_pct)
                
        elif action == 1: # AI wants to be NEUTRAL
            if has_pos:
                portfolio, trade_executed = self.close_position(portfolio, asset, current_price, "(Neutral Signal)")

        # Calculate Total Portfolio Value (Cash + Unlocked Cash + Floating PNL)
        total_val = portfolio["cash"]
        for p_asset, p_data in portfolio["positions"].items():
            total_val += p_data.get("locked_cash", 0)
            # Add floating PNL
            if p_data["type"] == "LONG":
                total_val += (current_price - p_data["entry_price"]) * p_data["amount"]
            else:
                total_val += (p_data["entry_price"] - current_price) * p_data["amount"]
                
        portfolio["total_value"] = total_val
        
        if trade_executed:
            self.log_trade(asset, current_price, action_str, conf, allocation_pct)
            
        return portfolio

    def check_stop_loss_take_profit(self, portfolio, asset, current_price):
        if asset not in portfolio["positions"]:
            return portfolio
            
        pos = portfolio["positions"][asset]
        entry = pos["entry_price"]
        
        if pos["type"] == "LONG":
            pct_change = (current_price - entry) / entry
        else: # SHORT
            pct_change = (entry - current_price) / entry
            
        if pct_change >= 0.02: # +2% Take Profit
            portfolio, _ = self.close_position(portfolio, asset, current_price, "(Take-Profit Hit!)")
            self.log_trade(asset, current_price, "TAKE_PROFIT", 1.0, 0.0)
        elif pct_change <= -0.01: # -1% Stop Loss
            portfolio, _ = self.close_position(portfolio, asset, current_price, "(Stop-Loss Hit!)")
            self.log_trade(asset, current_price, "STOP_LOSS", 1.0, 0.0)
            
        return portfolio

    def run_loop(self, poll_interval_sec=10):
        print(f"[+] Starting Professional Bi-Directional Engine (15m Timeframe).")
        while True:
            portfolio = self.load_portfolio() # Load fresh state once at the start of loop
            
            for asset in self.assets:
                df = self.fetch_live_data(asset)
                if df is not None:
                    current_price = df['close'].iloc[-1]
                    
                    portfolio = self.check_stop_loss_take_profit(portfolio, asset, current_price)
                    
                    state_vector, _ = self.construct_state_vector(df)
                    with torch.no_grad():
                        action = self.brain.get_action(state_vector, epsilon=0.0)
                    
                    conf = 1.0 if action in [0, 2] else 0.5
                    allocation = self.risk_manager.calculate_position_size(conf, 0.02, current_price)
                    
                    portfolio = self.execute_paper_trade(portfolio, asset, current_price, action, conf, allocation)
                    
            self.save_portfolio(portfolio) # Save state once all 5 assets are processed
            time.sleep(poll_interval_sec)

if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'data'), exist_ok=True)
    universe = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
    trader = PaperTrader(assets=universe)
    trader.run_loop(poll_interval_sec=15)
