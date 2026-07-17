import sys
import os
import pandas as pd
import numpy as np
import torch
import warnings

warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backtesting'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))

from quant_features import QuantFeatureEngineer
from trading_env import CryptoTradingEnv
from quant_agent import QuantAgent
from sentiment_agent import SentimentAgent
from risk_agent import RiskAgent
from meta_agent import MetaAgent

def extract_state_vector(state_dict, env, quant_agent, sentiment_agent):
    """Converts the environment MTF state dict into the 18-Dimensional Neural Network input tensor"""
    quant_conf = quant_agent.analyze(state_dict)
    sent_conf = sentiment_agent.analyze(state_dict.get('sentiment_score', 0.0))
    current_weight = (env.coin_held * state_dict['close']) / env.portfolio_value
    
    # Universal 15-Timeframe Feature Tensor
    state_vector = [
        quant_conf, 
        sent_conf, 
        current_weight,
        state_dict.get('1mo_z_score', 0.0),
        state_dict.get('1w_z_score', 0.0),
        state_dict.get('3d_z_score', 0.0),
        state_dict.get('1d_z_score', 0.0),
        state_dict.get('12h_volatility', 0.0),
        state_dict.get('8h_volatility', 0.0),
        state_dict.get('6h_volatility', 0.0),
        state_dict.get('4h_volatility', 0.0),
        state_dict.get('2h_volatility', 0.0),
        state_dict.get('1h_volatility', 0.0),
        state_dict.get('30m_volume_spike', 1.0),
        state_dict.get('15m_volume_spike', 1.0),
        state_dict.get('5m_volume_spike', 1.0),
        state_dict.get('3m_volume_spike', 1.0),
        state_dict.get('1m_volume_spike', 1.0)
    ]
    
    return state_vector, current_weight

def get_asset_features(asset, base_dir):
    print(f"\n[+] Extracting 15-Timeframe Institutional Features for {asset}...")
    engineer = QuantFeatureEngineer(asset_name=asset, data_dir=base_dir)
    engineer.calculate_macro_trend()
    engineer.calculate_base_trend()
    engineer.calculate_intermediate_volatility()
    engineer.calculate_micro_structure()
    engineer.merge_sentiment()
    
    final_df = engineer.get_features()
    
    if 'timestamp' in final_df.columns:
        final_df['timestamp'] = pd.to_datetime(final_df['timestamp'], utc=True)
        final_df.set_index('timestamp', inplace=True)
    return final_df.sort_index()

def train_universal_dqn(epochs_per_window=5):
    base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    UNIVERSE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    
    # Preload all 5 assets into memory to speed up multi-asset training
    portfolio_data = {}
    for asset in UNIVERSE:
        portfolio_data[asset] = get_asset_features(asset, base_dir)
        
    print("\n[+] Initializing Universal Meta-Agent (18-Dimensional Brain)...")
    
    # The brain now accepts 18 features!
    meta_agent = MetaAgent(input_dim=18, buffer_size=100000, batch_size=64)
    risk_agent = RiskAgent(target_daily_volatility=0.02, max_allocation=0.20)
    quant_agent = QuantAgent(z_score_threshold=2.0)
    sentiment_agent = SentimentAgent()
    
    epsilon = 1.0
    epsilon_min = 0.05
    epsilon_decay = 0.998 # Decays slower because we train on 5x more data!
    
    # Walk-Forward Setup (Option A splits applied to Universal Option B model)
    years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    best_overall_sharpe = -999.0
    
    print(f"\n[+] Commencing Universal Multi-Asset Training ({epochs_per_window} Epochs per Window)...")
    
    for year in years:
        print("\n" + "="*80)
        print(f"[*] WALKING FORWARD: Year {year}")
        print("="*80)
        
        if year == 2026:
            # Current year: Train Jan-Apr, Validate May-Present
            train_start, train_end = f"{year}-01-01", f"{year}-04-30"
            val_start, val_end = f"{year}-05-01", f"{year}-12-31"
        else:
            # Historical years: Train Jan-Sep, Validate Oct-Dec
            train_start, train_end = f"{year}-01-01", f"{year}-09-30"
            val_start, val_end = f"{year}-10-01", f"{year}-12-31"
        
        # --- UNIVERSAL TRAINING PHASE ---
        print(f"\n--- TRAINING PHASE (CROSS-ASSET): {train_start} to {train_end} ---")
        
        for epoch in range(1, epochs_per_window + 1):
            epoch_loss = 0
            epoch_steps = 0
            
            # Train the same brain across all 5 assets sequentially
            for asset in UNIVERSE:
                train_df = portfolio_data[asset].loc[train_start:train_end]
                if len(train_df) < 30: continue
                
                env = CryptoTradingEnv(train_df.reset_index(), initial_balance=10000.0)
                state_dict = env.reset()
                state_vec, c_weight = extract_state_vector(state_dict, env, quant_agent, sentiment_agent)
                
                done = False
                while not done:
                    action = meta_agent.get_action(state_vec, epsilon)
                    
                    if action == 2: raw_conf = 1.0
                    elif action == 0: raw_conf = 0.0
                    else: raw_conf = c_weight
                        
                    final_alloc = risk_agent.calculate_position_size(
                        meta_agent_confidence=raw_conf,
                        current_atr=state_dict.get('ATR_14', 0.0),
                        current_price=state_dict['close']
                    )
                    
                    next_state_dict, reward, done, _ = env.step(final_alloc)
                    next_state_vec, n_c_weight = extract_state_vector(next_state_dict, env, quant_agent, sentiment_agent)
                    
                    meta_agent.remember(state_vec, action, reward, next_state_vec, float(done))
                    loss = meta_agent.train_step()
                    epoch_loss += loss
                    
                    if epoch_steps % 100 == 0:
                        meta_agent.update_target_network()
                        
                    state_dict = next_state_dict
                    state_vec = next_state_vec
                    c_weight = n_c_weight
                    epoch_steps += 1
            
            if epsilon > epsilon_min:
                epsilon = max(epsilon_min, epsilon * epsilon_decay)
                
            avg_loss = epoch_loss / max(1, epoch_steps)
            print(f"Train Epoch {epoch:02d} | Eps: {epsilon:.2f} | Avg Cross-Asset Loss: {avg_loss:.4f}")

        # --- UNIVERSAL VALIDATION PHASE ---
        print(f"\n--- VALIDATION PHASE (CROSS-ASSET): {val_start} to {val_end} ---")
        val_sharpes = []
        val_returns = []
        
        for asset in UNIVERSE:
            val_df = portfolio_data[asset].loc[val_start:val_end]
            if len(val_df) < 10: continue
            
            val_env = CryptoTradingEnv(val_df.reset_index(), initial_balance=10000.0)
            state_dict = val_env.reset()
            state_vec, c_weight = extract_state_vector(state_dict, val_env, quant_agent, sentiment_agent)
            done = False
            
            while not done:
                # STRICT EVALUATION: Epsilon = 0
                action = meta_agent.get_action(state_vec, 0.0)
                if action == 2: raw_conf = 1.0
                elif action == 0: raw_conf = 0.0
                else: raw_conf = c_weight
                    
                final_alloc = risk_agent.calculate_position_size(
                    meta_agent_confidence=raw_conf,
                    current_atr=state_dict.get('ATR_14', 0.0),
                    current_price=state_dict['close']
                )
                
                next_state_dict, _, done, _ = val_env.step(final_alloc)
                state_vec, c_weight = extract_state_vector(next_state_dict, val_env, quant_agent, sentiment_agent)
                state_dict = next_state_dict
                
            metrics = val_env.get_portfolio_metrics()
            val_sharpes.append(metrics['sharpe_ratio'])
            val_returns.append(metrics['total_return_pct'])
            print(f"  {asset} | Ret: {metrics['total_return_pct']:>6.2f}% | Sharpe: {metrics['sharpe_ratio']:>5.2f}")
            
        if not val_sharpes:
            continue
            
        avg_portfolio_sharpe = np.mean(val_sharpes)
        avg_portfolio_ret = np.mean(val_returns)
        
        print(f"=> Universal Portfolio Validation | Avg Ret: {avg_portfolio_ret:>6.2f}% | Avg Sharpe: {avg_portfolio_sharpe:>5.2f}")
        
        if avg_portfolio_sharpe > best_overall_sharpe:
            best_overall_sharpe = avg_portfolio_sharpe
            print(f"[!] New Best Universal Sharpe! Saving 'universal_meta_agent.pth'...")
            save_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'universal_meta_agent.pth')
            torch.save(meta_agent.q_network.state_dict(), save_path)
            
    print("\n" + "="*80)
    print(f"[OK] Universal Walk-Forward Validation Complete. Peak Unseen Portfolio Sharpe: {best_overall_sharpe:.2f}")

if __name__ == "__main__":
    train_universal_dqn(epochs_per_window=10)
