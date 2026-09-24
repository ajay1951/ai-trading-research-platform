import os
import sys
import pandas as pd
import numpy as np
import torch
import warnings

warnings.filterwarnings("ignore")
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backtesting'))

from quant_features import QuantFeatureEngineer
from risk_agent import RiskAgent
from meta_agent import MetaAgent

def run_cadence_experiment():
    print("[*] Testing Scalping Cadence & Noise Filtering Sweet Spot...")
    base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    
    dfs = {}
    for asset in assets:
        engineer = QuantFeatureEngineer(asset_name=asset, data_dir=base_dir, base_timeframe="1h")
        engineer.calculate_macro_trend()
        engineer.calculate_base_trend()
        engineer.calculate_intermediate_volatility()
        engineer.calculate_micro_structure()
        engineer.merge_sentiment()
        dfs[asset] = engineer.get_features().sort_index()

    common_idx = dfs[assets[0]].index
    for asset in assets[1:]:
        common_idx = common_idx.intersection(dfs[asset].index)
    common_idx = common_idx.sort_values()

    meta_agent = MetaAgent(input_dim=18, buffer_size=10000, batch_size=64)
    weights_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'universal_meta_agent.pth')
    if os.path.exists(weights_path):
        meta_agent.q_network.load_state_dict(torch.load(weights_path, map_location=meta_agent.device))
        meta_agent.q_network.eval()

    feature_cols = [
        '1mo_z_score', '1w_z_score', '3d_z_score', '1d_z_score',
        '12h_volatility', '8h_volatility', '6h_volatility', '4h_volatility',
        '2h_volatility', '1h_volatility', '30m_volume_spike', '15m_volume_spike',
        '5m_volume_spike', '3m_volume_spike', '1m_volume_spike', 'close', 'ATR_14', 'sentiment_score', 'funding_rate'
    ]
    
    asset_matrices = {}
    asset_closes = {}
    asset_atrs = {}
    asset_1mo_z = {}
    for asset in assets:
        df_aligned = dfs[asset].loc[common_idx]
        asset_closes[asset] = df_aligned['close'].values
        asset_atrs[asset] = df_aligned['ATR_14'].values if 'ATR_14' in df_aligned.columns else np.zeros(len(common_idx))
        asset_1mo_z[asset] = df_aligned['1mo_z_score'].values if '1mo_z_score' in df_aligned.columns else np.zeros(len(common_idx))
        cols_present = [c for c in feature_cols if c in df_aligned.columns]
        asset_matrices[asset] = df_aligned[cols_present].values

    btc_closes_series = pd.Series(asset_closes["BTCUSDT"])
    btc_100d_sma = btc_closes_series.rolling(window=2400, min_periods=1).mean().values

    # Test parameter configurations:
    # (cadence_hours, long_only, stop_trail_pct, min_order_pct)
    configs = [
        {"name": "1h Scalp (Long-Only, 5% trail, 5% band)", "cadence": 1, "long_only": True, "trail": 0.05, "band": 0.05},
        {"name": "4h Swing Scalp (Long-Only, 6% trail, 8% band)", "cadence": 4, "long_only": True, "trail": 0.06, "band": 0.08},
        {"name": "8h Intraday (Long-Only, 8% trail, 10% band)", "cadence": 8, "long_only": True, "trail": 0.08, "band": 0.10},
        {"name": "12h Momentum (Long-Only, 10% trail, 15% band)", "cadence": 12, "long_only": True, "trail": 0.10, "band": 0.15},
        {"name": "4h Long+Short (Adaptive trailing, 8% band)", "cadence": 4, "long_only": False, "trail": 0.06, "band": 0.08},
    ]

    FEE = 0.0002
    for cfg in configs:
        cadence = cfg["cadence"]
        long_only = cfg["long_only"]
        trail_base = cfg["trail"]
        band = cfg["band"]
        
        initial_cash = 50.0
        cash = initial_cash
        holdings = {a: 0.0 for a in assets}
        avg_entry = {a: 0.0 for a in assets}
        highest_p = {a: 0.0 for a in assets}
        lowest_p = {a: float('inf') for a in assets}
        trades = 0
        p_history = [cash]
        
        for i in range(len(common_idx)):
            c_prices = {a: asset_closes[a][i] for a in assets}
            tot_val = cash + sum(holdings[a] * c_prices[a] for a in assets)
            
            if i % cadence == 0 or i == len(common_idx) - 1:
                state_vecs = []
                for a in assets:
                    mat = asset_matrices[a][i]
                    z_macro = (mat[0] + mat[1]) if len(mat) > 1 else 0.0
                    z_micro = mat[3] if len(mat) > 3 else 0.0
                    blended_z = (z_macro * 0.4) + (z_micro * 0.6)
                    quant_conf = float(np.clip(0.5 - (blended_z / 4.0), 0.05, 0.95))
                    sent_conf = mat[17] if len(mat) > 17 else 0.5
                    if sent_conf == 0.0: sent_conf = 0.5
                    state_vecs.append([quant_conf, sent_conf, 0.0] + list(mat[:15]))
                
                with torch.no_grad():
                    tensor_batch = torch.FloatTensor(state_vecs).to(meta_agent.device)
                    q_vals = meta_agent.q_network(tensor_batch)
                    actions = torch.argmax(q_vals, dim=1).cpu().numpy()
                
                targets = {}
                for idx, a in enumerate(assets):
                    act = actions[idx]
                    cp = c_prices[a]
                    
                    if long_only:
                        conf = 0.8 if act == 2 else (0.3 if act == 1 else 0.0)
                    else:
                        conf = 0.8 if act == 2 else (0.3 if act == 1 else -0.5)
                        
                    targets[a] = conf * 0.3 # Allocate max 30% per coin
                    
                    if holdings[a] > 0:
                        highest_p[a] = max(highest_p[a], cp)
                    elif holdings[a] < 0:
                        lowest_p[a] = min(lowest_p[a], cp)

                # Execute rebalances
                for a in assets:
                    cp = c_prices[a]
                    target_v = tot_val * targets[a]
                    curr_v = holdings[a] * cp
                    diff = target_v - curr_v
                    
                    # Stop loss trigger
                    if holdings[a] > 0 and cp < highest_p[a] * (1.0 - trail_base):
                        diff = -curr_v # Sell all
                    elif holdings[a] < 0 and cp > lowest_p[a] * (1.0 + trail_base):
                        diff = -curr_v # Cover short
                        
                    if abs(diff) > max(2.0, tot_val * band):
                        amt = diff / cp
                        exec_p = cp * (1.0002 if diff > 0 else 0.9998)
                        cost = abs(amt) * exec_p
                        fee = cost * FEE
                        
                        if diff > 0:
                            cash -= (cost + fee)
                        else:
                            cash += (cost - fee)
                            
                        holdings[a] += amt
                        trades += 1
                        if abs(holdings[a]) < 1e-8:
                            holdings[a] = 0.0
                            highest_p[a] = 0.0
                            lowest_p[a] = float('inf')
                            
            tot_val = cash + sum(holdings[a] * c_prices[a] for a in assets)
            p_history.append(tot_val)
            
        final_v = p_history[-1]
        ret = ((final_v - initial_cash) / initial_cash) * 100.0
        print(f"  --> {cfg['name']:<48} | Final: ${final_v:>7.2f} | Return: {ret:>+6.1f}% | Trades: {trades:>5d}")

if __name__ == "__main__":
    run_cadence_experiment()
