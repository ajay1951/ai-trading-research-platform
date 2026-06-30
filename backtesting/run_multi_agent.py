import pandas as pd
import sys
import os
import warnings

warnings.filterwarnings("ignore")

# Add agents directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))

from quant_features import QuantFeatureEngineer
from trading_env import CryptoTradingEnv
from quant_agent import QuantAgent
from sentiment_agent import SentimentAgent
from risk_agent import RiskAgent
from meta_agent import MetaAgent

def run_backtest():
    print("1. Initializing Multi-Agent Council...")
    quant_agent = QuantAgent(z_score_threshold=2.0)
    sentiment_agent = SentimentAgent()
    risk_agent = RiskAgent(target_daily_volatility=0.02, max_allocation=0.20)
    meta_agent = MetaAgent() # Overarching General
    
    print("2. Loading Historical Data (BTC and ETH for Pairs Trading)...")
    btc_df = pd.read_csv("data/BTCUSDT_1d_historical.csv")
    eth_df = pd.read_csv("data/ETHUSDT_1d_historical.csv")
    sent_df = pd.read_csv("data/BTCUSDT_sentiment_2019_2026.csv")
    
    print("3. Generating StatArb Quant Features (BTC vs ETH Spread)...")
    engineer = QuantFeatureEngineer(btc_df, eth_df)
    engineer.calculate_atr(14).calculate_returns().calculate_spread_z_score(30)
    engineer.merge_sentiment(sent_df)
    final_df = engineer.get_features()
    
    print("4. Initializing Matrix Simulator...")
    env = CryptoTradingEnv(final_df, initial_balance=10000.0)
    
    print("\n5. Beginning 7-Year Backtest Simulation...")
    state = env.reset()
    done = False
    
    while not done:
        # Step 1: Sub-Agents analyze the market
        quant_conf = quant_agent.analyze(state['z_score'])
        sent_conf = sentiment_agent.analyze(state['sentiment'])
        
        # Step 2: The General (Meta-Agent) makes a decision
        current_weight = (env.coin_held * state['price']) / env.portfolio_value
        agent_state = [quant_conf, sent_conf, current_weight]
        
        action = meta_agent.get_action(agent_state, epsilon=0.0)
        
        if action == 2: # Buy
            raw_meta_confidence = 1.0
        elif action == 0: # Sell
            raw_meta_confidence = 0.0
        else: # Hold
            raw_meta_confidence = current_weight
            
        # Step 3: The Risk Agent aggressively sizes the trade using ATR Target Volatility
        final_allocation = risk_agent.calculate_position_size(
            meta_agent_confidence=raw_meta_confidence,
            current_atr=state['atr'],
            current_price=state['price']
        )
        
        # Step 4: Execute the trade in the matrix
        state, reward, done, _ = env.step(final_allocation)
        
    print("\n[OK] StatArb Backtest Complete!")
    metrics = env.get_portfolio_metrics()
    print("="*40)
    print(f"Final Balance: ${metrics['final_balance']:,.2f}")
    print(f"Total Return:  {metrics['total_return_pct']:.2f}%")
    print(f"Sharpe Ratio:  {metrics['sharpe_ratio']:.2f}")
    print("="*40)

if __name__ == "__main__":
    run_backtest()
