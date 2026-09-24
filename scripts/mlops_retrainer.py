import os
import sys
import pandas as pd
import numpy as np
import torch
from datetime import datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backtesting'))
from quant_features import QuantFeatureEngineer
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))
from meta_agent import MetaAgent

def continuous_learning_loop():
    print("=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting PyTorch Continuous Learning Pipeline (MLOps)")
    print("=" * 60)
    
    base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    
    print("[+] Syncing latest 30 days of market data and generating features...", flush=True)
    dfs = {}
    for asset in assets:
        engineer = QuantFeatureEngineer(asset_name=asset, data_dir=base_dir)
        engineer.calculate_macro_trend()
        engineer.calculate_base_trend()
        engineer.calculate_intermediate_volatility()
        engineer.calculate_micro_structure()
        engineer.merge_sentiment()
        try:
            engineer.merge_derivatives()
        except:
            pass
        
        df = engineer.get_features().sort_index()
        # Keep only the last 30 days (simulated)
        if len(df) > 8000:
            df = df.iloc[-8000:]
        dfs[asset] = df

    common_idx = dfs[assets[0]].index
    for asset in assets[1:]:
        common_idx = common_idx.intersection(dfs[asset].index)
    common_idx = common_idx.sort_values()
    
    print(f"[+] Synced {len(common_idx)} timesteps for fine-tuning.")
    
    # Init Meta Agent
    meta_agent = MetaAgent(input_dim=18, buffer_size=50000, batch_size=64, lr=0.0001)
    weights_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'universal_meta_agent.pth')
    
    if os.path.exists(weights_path):
        print(f"[*] Loading base weights from {weights_path}")
        meta_agent.q_network.load_state_dict(torch.load(weights_path, map_location=meta_agent.device))
    
    meta_agent.q_network.train()
    
    feature_cols = [
        '1mo_z_score', '1w_z_score', '3d_z_score', '1d_z_score',
        '12h_volatility', '8h_volatility', '6h_volatility', '4h_volatility',
        '2h_volatility', '1h_volatility', '30m_volume_spike', '15m_volume_spike',
        '5m_volume_spike', '3m_volume_spike', '1m_volume_spike', 'close', 'ATR_14', 'sentiment_score'
    ]
    
    asset_matrices = {}
    asset_closes = {}
    for asset in assets:
        df_aligned = dfs[asset].loc[common_idx]
        asset_closes[asset] = df_aligned['close'].values
        cols_present = [c for c in feature_cols if c in df_aligned.columns]
        
        # Ensure matrix is exactly 18 dims
        mat = df_aligned[cols_present].values
        if mat.shape[1] < 18:
            padding = np.zeros((mat.shape[0], 18 - mat.shape[1]))
            mat = np.hstack([mat, padding])
        asset_matrices[asset] = mat
        
    print("[+] Running Offline RL Episode to build Replay Buffer...")
    # Fill replay buffer based on simple perfect-hindsight momentum logic
    # If price goes up in next 3 steps -> BUY (2), down -> SELL (0)
    for i in range(len(common_idx) - 3):
        for asset in assets:
            c_price = asset_closes[asset][i]
            future_price = asset_closes[asset][i+3]
            ret = (future_price - c_price) / c_price
            
            if ret > 0.002: action = 2
            elif ret < -0.002: action = 0
            else: action = 1
            
            reward = ret * 100.0 if action == 2 else (-ret * 100.0 if action == 0 else 0.0)
            
            state = [0.5, 0.5, 0.0] + list(asset_matrices[asset][i][:15])
            next_state = [0.5, 0.5, 0.0] + list(asset_matrices[asset][i+1][:15])
            
            meta_agent.remember(state, action, reward, next_state, False)
            
    print(f"[*] Memory Buffer populated with {len(meta_agent.memory)} transitions.")
    print("[+] Fine-tuning Q-Network (5 Epochs)...")
    
    losses = []
    for epoch in range(5):
        epoch_loss = 0
        batches = len(meta_agent.memory) // meta_agent.batch_size
        for _ in range(min(500, batches)): # limit per epoch for speed
            loss = meta_agent.train_step()
            epoch_loss += loss
            
        print(f"  - Epoch {epoch+1}/5 | Avg Loss: {epoch_loss/max(1, min(500, batches)):.4f}")
        
    meta_agent.update_target_network()
    
    print(f"[*] Saving Fine-Tuned PyTorch Weights to {weights_path}")
    torch.save(meta_agent.q_network.state_dict(), weights_path)
    print("[OK] MLOps Pipeline Complete. Live Trader will auto-load the new weights.")
    print("=" * 60)

if __name__ == "__main__":
    continuous_learning_loop()
