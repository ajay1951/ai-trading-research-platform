import sys
import os
import pandas as pd
import numpy as np
import torch
import warnings
from collections import deque

warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backtesting'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))

from quant_features import QuantFeatureEngineer
from transformer_agent import TransformerMetaAgent

def extract_state_vector(state_dict, current_weight):
    """Converts the environment dict into the 19-Dimensional Neural Network input tensor"""
    # Simulate L2 Order Book Imbalance (OBI) using volume spikes during training
    # Real L2 data is used in live_trader.py
    simulated_obi = (state_dict.get('1m_volume_spike', 1.0) - 1.0) * 0.1 
    
    state_vector = [
        0.5, # Placeholder for quant conf
        0.5, # Placeholder for sentiment
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
        state_dict.get('1m_volume_spike', 1.0),
        simulated_obi # 19th Dimension: L2 Proxy
    ]
    
    return [0.0 if np.isnan(x) or np.isinf(x) else float(x) for x in state_vector]

def get_asset_features(asset, base_dir):
    print(f"\n[+] Extracting Transformer Features for {asset}...")
    engineer = QuantFeatureEngineer(asset_name=asset, data_dir=base_dir)
    engineer.calculate_macro_trend()
    engineer.calculate_base_trend()
    engineer.calculate_intermediate_volatility()
    engineer.calculate_micro_structure()
    
    final_df = engineer.get_features()
    
    if 'timestamp' in final_df.columns:
        final_df['timestamp'] = pd.to_datetime(final_df['timestamp'], utc=True)
        final_df.set_index('timestamp', inplace=True)
    return final_df.sort_index()

def train_transformer(epochs_per_window=3):
    base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    UNIVERSE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    SEQ_LEN = 10
    
    portfolio_data = {}
    for asset in UNIVERSE:
        portfolio_data[asset] = get_asset_features(asset, base_dir)
        
    print(f"\n[+] Initializing High-Frequency Transformer (19-Dim, Sequence={SEQ_LEN})...")
    
    agent = TransformerMetaAgent(input_dim=19, seq_len=SEQ_LEN, d_model=64, nhead=4, num_layers=2, output_dim=3)
    
    epsilon = 1.0
    epsilon_min = 0.05
    epsilon_decay = 0.999
    
    years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    
    for year in years:
        print(f"\n[*] WALKING FORWARD: Year {year}")
        
        for epoch in range(epochs_per_window):
            total_loss = 0
            steps = 0
            
            for asset in UNIVERSE:
                df = portfolio_data[asset]
                df_year = df[df.index.year == year]
                if df_year.empty: continue
                
                # We need to build a sequence buffer
                sequence_buffer = deque(maxlen=SEQ_LEN)
                current_weight = 0.0
                
                # We will process the dataframe row by row to build sequences
                for i in range(len(df_year) - 1):
                    current_row = df_year.iloc[i].to_dict()
                    next_row = df_year.iloc[i+1].to_dict()
                    
                    state_vec = extract_state_vector(current_row, current_weight)
                    sequence_buffer.append(state_vec)
                    
                    if len(sequence_buffer) < SEQ_LEN:
                        continue
                        
                    # Calculate Reward based on price action
                    price_change = (next_row['close'] - current_row['close']) / current_row['close']
                    
                    # Get Action from Transformer
                    action = agent.get_action(list(sequence_buffer), epsilon)
                    
                    if action == 2: # LONG
                        reward = price_change * 100
                        current_weight = 1.0
                    elif action == 0: # SHORT
                        reward = -price_change * 100
                        current_weight = -1.0
                    else:
                        reward = -0.01 # Small penalty for holding to encourage trading
                        current_weight = 0.0
                        
                    next_state_vec = extract_state_vector(next_row, current_weight)
                    
                    # We need the NEXT sequence to store in memory
                    next_sequence = list(sequence_buffer)[1:] + [next_state_vec]
                    
                    agent.remember(list(sequence_buffer), action, reward, next_sequence, done=False)
                    loss = agent.train_step()
                    
                    total_loss += loss
                    steps += 1
                    
                    if epsilon > epsilon_min:
                        epsilon *= epsilon_decay
                        
            print(f"  - Epoch {epoch+1}/{epochs_per_window} | Loss: {total_loss/max(1, steps):.4f} | Epsilon: {epsilon:.4f}")
            agent.update_target_network()
            
    # Save Model
    model_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'transformer_meta_agent_5m.pth')
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    torch.save(agent.q_network.state_dict(), model_path)
    print(f"\n[SUCCESS] Transformer Weights saved to {model_path}")

if __name__ == "__main__":
    train_transformer()
