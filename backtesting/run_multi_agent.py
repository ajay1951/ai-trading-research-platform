import os
import sys
import pandas as pd
import numpy as np
import torch
import warnings

warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))

from quant_features import QuantFeatureEngineer
from trading_env import CryptoTradingEnv
from quant_agent import QuantAgent
from sentiment_agent import SentimentAgent
from risk_agent import RiskAgent
from meta_agent import MetaAgent

def extract_state_vector(state_dict, env, quant_agent, sentiment_agent):
    quant_conf = quant_agent.analyze(state_dict)
    sent_conf = state_dict.get('sentiment_score', 0.5) 
    if sent_conf == 0.0: sent_conf = 0.5
    current_weight = (env.coin_held * state_dict['close']) / env.portfolio_value
    
    state_vector = [
        quant_conf, sent_conf, current_weight,
        state_dict.get('1mo_z_score', 0.0), state_dict.get('1w_z_score', 0.0),
        state_dict.get('3d_z_score', 0.0), state_dict.get('1d_z_score', 0.0),
        state_dict.get('12h_volatility', 0.0), state_dict.get('8h_volatility', 0.0),
        state_dict.get('6h_volatility', 0.0), state_dict.get('4h_volatility', 0.0),
        state_dict.get('2h_volatility', 0.0), state_dict.get('1h_volatility', 0.0),
        state_dict.get('30m_volume_spike', 1.0), state_dict.get('15m_volume_spike', 1.0),
        state_dict.get('5m_volume_spike', 1.0), state_dict.get('3m_volume_spike', 1.0),
        state_dict.get('1m_volume_spike', 1.0)
    ]
    return state_vector, current_weight

def run_backtest():
    print("1. Initializing Multi-Agent Council...", flush=True)
    quant_agent = QuantAgent(2.0)
    sentiment_agent = SentimentAgent()
    risk_agent = RiskAgent(0.02, 0.20)
    
    meta_agent = MetaAgent(input_dim=18, buffer_size=100000, batch_size=64)
    weights_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'universal_meta_agent.pth')
    
    if os.path.exists(weights_path):
        print(f"[+] Loading trained weights from: {weights_path}", flush=True)
        meta_agent.q_network.load_state_dict(torch.load(weights_path, map_location=meta_agent.device))
        meta_agent.q_network.eval()
    else:
        print(f"[!] Warning: Weights file not found at {weights_path}. Running default policy.", flush=True)

    base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    
    print("\n2. Executing Multi-Asset Evaluation (2019–2026)...", flush=True)
    print("="*60, flush=True)
    
    for asset in assets:
        try:
            print(f"[*] Evaluating {asset:<8} across 2019-2026 5m history...", flush=True)
            engineer = QuantFeatureEngineer(asset_name=asset, data_dir=base_dir)
            engineer.calculate_macro_trend()
            engineer.calculate_base_trend()
            engineer.calculate_intermediate_volatility()
            engineer.calculate_micro_structure()
            engineer.merge_sentiment()
            df = engineer.get_features().sort_index()
            
            env = CryptoTradingEnv(df.reset_index(), initial_balance=50.0)
            state_dict = env.reset()
            state_vec, c_weight = extract_state_vector(state_dict, env, quant_agent, sentiment_agent)
            done = False
            
            step_counter = 0
            while not done:
                step_counter += 1
                if step_counter % 3 == 0 or done:
                    action = meta_agent.get_action(state_vec, epsilon=0.0)
                    if action == 2: raw_conf = 1.0
                    elif action == 0: raw_conf = 0.0
                    else: raw_conf = c_weight
                        
                    # Dynamic Allocation Scaling: In strong Bull runs (1mo_z_score > 0), scale max_alloc up to 80%
                    z_score_1mo = state_dict.get('1mo_z_score', 0.0)
                    if z_score_1mo > 1.0:
                        dynamic_max_alloc = 0.80 # Full Aggressive Bull Allocation
                    elif z_score_1mo > 0.0:
                        dynamic_max_alloc = 0.50 # Moderate Bull Allocation
                    else:
                        dynamic_max_alloc = 0.20 # Defensive Allocation
                        
                    target_alloc = risk_agent.calculate_position_size(
                        final_confidence=raw_conf,
                        current_atr=state_dict.get('ATR_14', 0.0),
                        current_price=state_dict['close'],
                        dynamic_max_alloc=dynamic_max_alloc
                    )
                    
                    # Hysteresis Filter: Only rebalance if allocation changes by > 5%
                    if abs(target_alloc - c_weight) > 0.05:
                        final_alloc = target_alloc
                    else:
                        final_alloc = c_weight
                    
                    next_state_dict, _, done, _ = env.step(final_alloc)
                    next_state_vec, n_c_weight = extract_state_vector(next_state_dict, env, quant_agent, sentiment_agent)
                    state_dict = next_state_dict
                    state_vec = next_state_vec
                    c_weight = n_c_weight
                else:
                    next_state_dict, _, done, _ = env.step(c_weight)
                    next_state_vec, n_c_weight = extract_state_vector(next_state_dict, env, quant_agent, sentiment_agent)
                    state_dict = next_state_dict
                    state_vec = next_state_vec
                    c_weight = n_c_weight
                
            metrics = env.get_portfolio_metrics()
            
            # Benchmark (Buy & Hold) calculation
            initial_price = df['close'].iloc[0]
            final_price = df['close'].iloc[-1]
            bnh_return_pct = ((final_price - initial_price) / initial_price) * 100.0
            
            # Buy & Hold Sharpe calculation
            returns = df['close'].pct_change().dropna()
            mean_ret = returns.mean()
            std_ret = returns.std()
            bnh_sharpe = (mean_ret / std_ret) * (365 * 288)**0.5 if std_ret > 0 else 0.0
            
            print(f"  {asset:<8} | AI Bal: ${metrics['final_balance']:>8,.2f} | AI Ret: {metrics['total_return_pct']:>6.2f}% | AI Sharpe: {metrics['sharpe_ratio']:>5.2f} | Trades: {metrics.get('total_trades', 0):>4d}")
            print(f"           | B&H Ret: {bnh_return_pct:>6.2f}% | B&H Sharpe: {bnh_sharpe:>5.2f} | AI Outperformance: {metrics['total_return_pct'] - bnh_return_pct:>+6.2f}%")
            print("-" * 60, flush=True)
        except Exception as e:
            print(f"  [!] Error evaluating {asset}: {e}")

    print("="*60)
    print("✅ Multi-Agent Backtest Simulation Complete!")

if __name__ == "__main__":
    run_backtest()
