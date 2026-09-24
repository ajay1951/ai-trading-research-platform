import sys
import os
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
import multiprocessing

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backtesting'))
from quant_features import QuantFeatureEngineer

# 🌟 RTX 2050 కోసం డిజైన్ చేయబడిన డీప్ న్యూరల్ నెట్‌వర్క్ (LSTM Version)
class CryptoRTXLSTM(nn.Module):
    def __init__(self, input_dim, hidden_dim=64, num_layers=2):
        super(CryptoRTXLSTM, self).__init__()
        # FP16 operations expect batch_first=True
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.3)
        self.fc1 = nn.Linear(hidden_dim, 32)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.2)
        self.fc2 = nn.Linear(32, 2)
        
    def forward(self, x):
        # x is (batch_size, seq_len, features)
        lstm_out, _ = self.lstm(x)
        # Extract the output of the last time step in the sequence
        last_out = lstm_out[:, -1, :]
        out = self.fc1(last_out)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        return out

class SequenceDataset(torch.utils.data.Dataset):
    """Generates 50-candle overlapping sequential windows for LSTM."""
    def __init__(self, features, targets, seq_len=50):
        self.features = features
        self.targets = targets
        self.seq_len = seq_len
        
    def __len__(self):
        return len(self.features) - self.seq_len + 1
        
    def __getitem__(self, idx):
        x = self.features[idx : idx + self.seq_len]
        y = self.targets[idx + self.seq_len - 1]
        # Standard FP32 casting, AMP will handle down-casting internally
        return torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.long)

def train_pytorch_isolated(X_train_scaled, y_train, X_test_scaled, y_test, feature_cols, device_name, all_test_dfs, horizon, fee, return_dict):
    device = torch.device(device_name)
    print("\n=======================================================")
    print("[*] Training Universal PyTorch LSTM Model via Ampere CUDA Cores (FP16)...")
    print("=======================================================")
    
    SEQ_LEN = 50
    train_dataset = SequenceDataset(X_train_scaled, y_train, seq_len=SEQ_LEN)
    train_loader = DataLoader(train_dataset, batch_size=2048, shuffle=True, pin_memory=True)
    
    pytorch_model = CryptoRTXLSTM(len(feature_cols)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(pytorch_model.parameters(), lr=0.001)
    
    # Initialize Automatic Mixed Precision Scaler to prevent FP16 gradients from exploding
    scaler = torch.cuda.amp.GradScaler()
    
    pytorch_model.train()
    for epoch in range(5):
        epoch_loss = 0.0
        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(device), batch_y.to(device)
            
            optimizer.zero_grad()
            
            # Forward pass inside autocast context
            with torch.cuda.amp.autocast():
                outputs = pytorch_model(batch_X)
                loss = criterion(outputs, batch_y)
                
            # Backward pass scaled by AMP
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            
            epoch_loss += loss.item()
            
        print(f"    Epoch {epoch+1}/5 | Loss: {epoch_loss/len(train_loader):.4f}")
        
    pytorch_model.eval()
    
    test_dataset = SequenceDataset(X_test_scaled, y_test, seq_len=SEQ_LEN)
    test_loader = DataLoader(test_dataset, batch_size=2048, shuffle=False)
    
    all_test_probs = []
    with torch.no_grad():
        for batch_X, _ in test_loader:
            batch_X = batch_X.to(device)
            logits = pytorch_model(batch_X)
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
            all_test_probs.extend(probs)
            
    pytorch_probs = np.concatenate([np.zeros(SEQ_LEN - 1), np.array(all_test_probs)])
    
    # Run Evaluation for Rich Checkpoint
    threshold = 0.72
    gross_return = 0.0
    net_return = 0.0
    num_trades = 0
    winning_trades = 0
    all_trades = []
    
    current_idx = 0
    for test_df in all_test_dfs:
        asset_name = test_df['asset'].iloc[0]
        asset_probs = pytorch_probs[current_idx:current_idx + len(test_df)]
        returns_arr = test_df['forward_return'].values
        
        atr_pct_arr = test_df['ATR_pct'].values
        
        in_position = False
        exit_index = 0
        
        for i in range(len(asset_probs)):
            if in_position and i >= exit_index:
                in_position = False
                
            if not in_position and asset_probs[i] >= threshold:
                # DYNAMIC SLIPPAGE (Base 0.1% + 50% of asset's volatility penalty)
                slippage = 0.001 + (atr_pct_arr[i] * 0.5)
                
                # VOLATILITY FILTER
                if slippage > 0.004:
                    continue
                    
                in_position = True
                exit_index = i + horizon
                trade_gross = returns_arr[i]
                
                trade_net = trade_gross - slippage
                
                gross_return += trade_gross
                net_return += trade_net
                num_trades += 1
                if trade_gross > fee:
                    winning_trades += 1
                    
                trade_date = test_df.index[i].strftime('%Y-%m-%d %H:%M')
                all_trades.append({
                    "Timestamp": trade_date,
                    "Asset": asset_name,
                    "Gross_PnL": float(trade_gross),
                    "Net_PnL": float(trade_net)
                })
        
        current_idx += len(test_df)
        
    win_rate = (winning_trades / num_trades) if num_trades > 0 else 0.0
    
    # Save the Rich Checkpoint
    checkpoint = {
        'model_state_dict': pytorch_model.state_dict(),
        'architecture': 'CryptoRTXLSTM',
        'features': feature_cols,
        'backtest_performance': {
            'total_trades': num_trades,
            'win_rate': win_rate,
            'net_pnl': net_return,
            'gross_pnl': gross_return,
            'trade_history': all_trades
        }
    }
    os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'models', 'weights'), exist_ok=True)
    torch.save(checkpoint, os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'universal_crypto_rtx_lstm.pth'))
    print("[*] Saved FP16 LSTM Rich Checkpoint (with Trade Metadata) to universal_crypto_rtx_lstm.pth")
    
    return_dict['pytorch_probs'] = pytorch_probs

def generate_dataset(asset="BTCUSDT"):
    print(f"[*] Generating Point-In-Time Features for {asset}...")
    base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    engineer = QuantFeatureEngineer(asset_name=asset, data_dir=base_dir, base_timeframe="5m")
    engineer.calculate_macro_trend()
    engineer.calculate_base_trend()
    engineer.calculate_intermediate_volatility()
    engineer.calculate_micro_structure()
    engineer.calculate_advanced_ohlcv()
    engineer.merge_derivatives()
    engineer.merge_macro_economic_data()
    
    df = engineer.get_features()
    if df.empty:
        raise ValueError(f"Feature dataframe for {asset} is empty.")
        
    # 2. న్యూస్ సెంటిమెంట్ డేటా విలీనం
    news_path = os.path.join(base_dir, f"{asset}_sentiment_2019_2026.csv")
    if os.path.exists(news_path):
        # print(f"[*] Merging Historical News Sentiment for {asset}...")
        news_df = pd.read_csv(news_path, parse_dates=['timestamp']).set_index('timestamp')
        
        # Ensure timezone compatibility before joining
        if df.index.tz is not None and news_df.index.tz is None:
            news_df.index = news_df.index.tz_localize(df.index.tz)
        elif df.index.tz is None and news_df.index.tz is not None:
            news_df.index = news_df.index.tz_localize(None)
            
        df = df.join(news_df['sentiment_score'], how='left').fillna({'sentiment_score': 0.0})
    else:
        df['sentiment_score'] = 0.0
        
    HORIZON = 12         
    FEE = 0.0015         
    PROFIT_TARGET = 0.0025 

    df[f'next_close_{HORIZON}'] = df['close'].shift(-HORIZON)
    df['forward_return'] = (df[f'next_close_{HORIZON}'] - df['close']) / df['close']
    
    # Volatility-Adjusted Labelling: Target based on half of the 14-period ATR
    df['ATR_pct'] = df['ATR_14'] / df['close']
    df['target'] = (df['forward_return'] > (df['ATR_pct'] * 0.5)).astype(int)
    
    features = [
        '1mo_z_score', '1w_z_score', '3d_z_score', '1d_z_score', 
        '12h_volatility', '8h_volatility', '6h_volatility', '4h_volatility', '2h_volatility', '1h_volatility', 
        '30m_volume_spike', '15m_volume_spike', '5m_volume_spike', '3m_volume_spike', '1m_volume_spike', 
        'ATR_14', 'log_return', 'RSI_14', 'MACD', 'MACD_hist', 'BB_Width',
        'funding_rate', 'open_interest', 'sentiment_score', 'DXY', 'SPX', 'TNX'
    ]
    
    # Purge infinite values which instantly destroy FP16 precision
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return df.dropna(subset=[f'next_close_{HORIZON}']), features, HORIZON, FEE

def run_benchmark():
    # 🌟 CUDA డిటెక్షన్ (RTX 2050 యాక్టివేట్ అవుతుంది)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"=======================================================")
    print(f"[*] HARDWARE: NVIDIA RTX 2050 4GB VRAM detected.")
    print(f"[*] RUNNING ON DEVICE: {device}")
    print(f"=======================================================")

    assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    all_train_dfs = []
    all_test_dfs = []
    feature_cols = None
    horizon = None
    fee = None
    
    print(f"[*] Aggregating Universal Dataset across {len(assets)} assets...")
    for asset in assets:
        try:
            df, f_cols, h, f = generate_dataset(asset)
            feature_cols = f_cols
            horizon = h
            fee = f
            
            train_df = df[(df.index.year >= 2019) & (df.index.year <= 2024)].copy()
            test_df = df[df.index.year == 2026].copy()
            
            train_df['asset'] = asset
            test_df['asset'] = asset
            
            all_train_dfs.append(train_df)
            all_test_dfs.append(test_df)
        except Exception as e:
            print(f"[!] Error generating data for {asset}: {e}")

    master_train_df = pd.concat(all_train_dfs)
    master_test_df = pd.concat(all_test_dfs)
    
    # We DO NOT shuffle the rows here anymore! Shuffling ruins chronological sequences for LSTM.
    # The DataLoader (shuffle=True) will shuffle the 50-candle overlapping sequences instead.
    
    print(f"[*] Total Universal Training Rows (2019-2024): {len(master_train_df)}")
    print(f"[*] Total Universal Testing Rows (2026): {len(master_test_df)}")
    
    X_train_raw = master_train_df[feature_cols].values
    X_test_raw = master_test_df[feature_cols].values
    y_train = master_train_df['target'].values
    y_test = master_test_df['target'].values
    
    # We need scaled data for Neural Nets and SVM
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_raw)
    X_test_scaled = scaler.transform(X_test_raw)
    
    import joblib
    os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'models', 'weights'), exist_ok=True)
    joblib.dump(scaler, os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'scaler.pkl'))
    
    # --- 1. PYTORCH DEEP LEARNING MODEL (ISOLATED PROCESS) ---
    manager = multiprocessing.Manager()
    return_dict = manager.dict()
    
    device_name = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    # We spawn a completely separate background process to train PyTorch.
    # When this process dies, Windows violently reclaims 100% of the VRAM.
    p = multiprocessing.Process(target=train_pytorch_isolated, args=(
        X_train_scaled, y_train, X_test_scaled, y_test, 
        feature_cols, device_name, all_test_dfs, horizon, fee, return_dict
    ))
    p.start()
    p.join()
    
    if 'pytorch_probs' in return_dict:
        pytorch_probs = return_dict['pytorch_probs']
    else:
        print("[!] Warning: PyTorch process crashed or returned no probabilities.")
        pytorch_probs = np.zeros(len(X_test_scaled))
        
    # --- 2. CLASSIC MACHINE LEARNING MODELS ---
    print("\n=======================================================")
    print("[*] Training Classic Machine Learning Models (CPU/GPU)...")
    print("=======================================================")
    
    models = {
        "CatBoost (Raw Data)": CatBoostClassifier(
            iterations=200, learning_rate=0.05, depth=4, 
            auto_class_weights='Balanced', random_seed=42, verbose=0,
            task_type='GPU'
        ),
        "LightGBM (Raw Data)": LGBMClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=5,
            is_unbalance=True, random_state=42, verbose=-1
        )
        # Skipped MLP and SVM to speed up benchmarking
    }
    
    all_predictions = {"PyTorch RTX 2050": pytorch_probs}
    
    for name, model in models.items():
        print(f"[*] Training {name}...")
        if "Scaled" in name:
            model.fit(X_train_scaled, y_train)
            raw_preds = model.predict_proba(X_test_scaled)
        else:
            model.fit(X_train_raw, y_train)
            raw_preds = model.predict_proba(X_test_raw)
            
        if raw_preds.ndim == 1:
            all_predictions[name] = 1 / (1 + np.exp(-raw_preds))
        else:
            all_predictions[name] = raw_preds[:, 1]
            
    # --- 3. EVALUATION ---
    print("\n=======================================================")
    print(" UNIVERSAL SUPER-BENCHMARK RESULTS (OOS 2026)")
    print("=======================================================\n")
    
    all_trades = []
    
    for name, probs in all_predictions.items():
        if "SVM" in name:
            threshold = 0.52
        elif "PyTorch" in name or "MLP" in name:
            threshold = 0.72
        else:
            threshold = 0.60
        
        gross_return = 0.0
        net_return = 0.0
        num_trades = 0
        winning_trades = 0
        
        current_idx = 0
        
        # Evaluate chronologically per asset so exit_index logic works flawlessly
        for test_df in all_test_dfs:
            asset_name = test_df['asset'].iloc[0]
            asset_probs = probs[current_idx:current_idx + len(test_df)]
            returns_arr = test_df['forward_return'].values
            
            atr_pct_arr = test_df['ATR_pct'].values
            
            in_position = False
            exit_index = 0
            
            for i in range(len(asset_probs)):
                if in_position and i >= exit_index:
                    in_position = False
                    
                if not in_position and asset_probs[i] >= threshold:
                    # DYNAMIC SLIPPAGE
                    slippage = 0.001 + (atr_pct_arr[i] * 0.5)
                    
                    if slippage > 0.004:
                        continue
                        
                    in_position = True
                    exit_index = i + horizon
                    trade_gross = returns_arr[i]
                    
                    trade_net = trade_gross - slippage
                    
                    gross_return += trade_gross
                    net_return += trade_net
                    num_trades += 1
                    if trade_gross > fee:
                        winning_trades += 1
                        
                    trade_date = test_df.index[i].strftime('%Y-%m-%d %H:%M')
                    all_trades.append({
                        "Model": name,
                        "Asset": asset_name,
                        "Timestamp": trade_date,
                        "Trade_Number": num_trades,
                        "Gross_PnL": trade_gross,
                        "Net_PnL": trade_net
                    })
                    
                    if "PyTorch" in name:
                        print(f"    [+] {trade_date} | {asset_name} | Trade {num_trades} | Net P&L: {trade_net*100:.2f}%")
            
            # Increment the index window for the next asset
            current_idx += len(test_df)
                    
        STARTING_BALANCE = 50.00
        dollar_profit = STARTING_BALANCE * net_return
        ending_balance = STARTING_BALANCE + dollar_profit
        
        print(f"--- {name} ---")
        print(f"Threshold:       {threshold * 100}%")
        print(f"Trades:          {num_trades}")
        print(f"Gross P&L (%):   {gross_return * 100:.2f}%")
        print(f"Net P&L (%):     {net_return * 100:.2f}% (After Dynamic Slippage)")
        print(f"Starting Bal:    ${STARTING_BALANCE:.2f}")
        print(f"Ending Bal:      ${ending_balance:.2f} (Profit: ${dollar_profit:.2f})")
        if num_trades > 0:
            print(f"Win Rate:        {(winning_trades / num_trades) * 100:.2f}%")
        print("-------------------------------------------------------\n")
        
    trades_df = pd.DataFrame(all_trades)
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'benchmark_trades_universal_2026.csv')
    trades_df.to_csv(csv_path, index=False)
    print(f"[*] Successfully saved every individual trade to: {csv_path}")

if __name__ == "__main__":
    run_benchmark()
