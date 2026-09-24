import os
import sys
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.preprocessing import StandardScaler
import multiprocessing

sys.path.append(os.path.dirname(__file__))
from benchmark_models import CryptoRTXLSTM, SequenceDataset, generate_dataset

def wfo_train_pytorch_isolated(X_train_scaled, y_train, X_test_scaled, y_test, feature_cols, device_name, return_dict):
    device = torch.device(device_name)
    SEQ_LEN = 50
    
    train_dataset = SequenceDataset(X_train_scaled, y_train, seq_len=SEQ_LEN)
    train_loader = DataLoader(train_dataset, batch_size=2048, shuffle=True, pin_memory=True)
    
    pytorch_model = CryptoRTXLSTM(len(feature_cols)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(pytorch_model.parameters(), lr=0.001)
    
    scaler = torch.amp.GradScaler('cuda')
    pytorch_model.train()
    
    for epoch in range(5):
        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(device), batch_y.to(device)
            optimizer.zero_grad()
            with torch.amp.autocast('cuda'):
                outputs = pytorch_model(batch_X)
                loss = criterion(outputs, batch_y)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            
    pytorch_model.eval()
    test_dataset = SequenceDataset(X_test_scaled, y_test, seq_len=SEQ_LEN)
    test_loader = DataLoader(test_dataset, batch_size=2048, shuffle=False)
    
    all_test_probs = []
    with torch.no_grad():
        for batch_X, _ in test_loader:
            batch_X = batch_X.to(device)
            with torch.amp.autocast('cuda'):
                logits = pytorch_model(batch_X)
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
            all_test_probs.extend(probs)
            
    # Pad to match original length due to sequencing
    pytorch_probs = np.concatenate([np.zeros(SEQ_LEN - 1), np.array(all_test_probs)])
    return_dict['pytorch_probs'] = pytorch_probs


def run_wfo():
    print("=======================================================")
    print(" 🏛️ INSTITUTIONAL WALK-FORWARD OPTIMIZATION (PyTorch AMP)")
    print("=======================================================")
    
    device_name = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    print(f"[*] Aggregating WFO Dataset across {len(assets)} assets...")
    
    all_asset_dfs = []
    feature_cols = None
    horizon = None
    
    for asset in assets:
        try:
            df, f_cols, h, _ = generate_dataset(asset)
            df['asset'] = asset
            feature_cols = f_cols
            horizon = h
            all_asset_dfs.append(df)
        except Exception as e:
            print(f"[!] Error generating data for {asset}: {e}")

    master_df = pd.concat(all_asset_dfs)
    
    test_years = [2022, 2023, 2024, 2025, 2026]
    threshold = 0.72 # GOLDILOCKS ZONE
    LEVERAGE = 3.0   # INSTITUTIONAL 3x LEVERAGE
    
    total_wfo_trades = 0
    total_wfo_gross = 0.0
    total_wfo_net = 0.0
    total_wfo_wins = 0
    
    current_compounded_balance = 50.0  # Real-world dynamic dollar tracking
    MAX_NOTIONAL_SIZE = 25000.0        # Liquid order book capacity limit
    
    for test_year in test_years:
        train_start = 2019 # EXPANDING WINDOW: Always keep past memory
        train_end = test_year - 1
        
        print(f"\n=======================================================")
        print(f" WFO FOLD: Train [{train_start}-{train_end}] --> Trade [{test_year}]")
        print(f"=======================================================")
        
        train_df = master_df[(master_df.index.year >= train_start) & (master_df.index.year <= train_end)]
        test_df = master_df[master_df.index.year == test_year]
        
        if test_df.empty or train_df.empty:
            print(f"[!] Skipping {test_year} due to lack of data.")
            continue
            
        X_train_raw = train_df[feature_cols].values
        X_test_raw = test_df[feature_cols].values
        y_train = train_df['target'].values
        y_test = test_df['target'].values
        
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train_raw)
        X_test_scaled = scaler.transform(X_test_raw)
        
        manager = multiprocessing.Manager()
        return_dict = manager.dict()
        
        # Isolate PyTorch to clear VRAM after every fold
        p = multiprocessing.Process(target=wfo_train_pytorch_isolated, args=(
            X_train_scaled, y_train, X_test_scaled, y_test, 
            feature_cols, device_name, return_dict
        ))
        p.start()
        p.join()
        
        if 'pytorch_probs' not in return_dict:
            print(f"[!] PyTorch failed in {test_year}")
            continue
            
        pytorch_probs = return_dict['pytorch_probs']
        
        fold_gross = 0.0
        fold_net = 0.0
        fold_trades = 0
        fold_wins = 0
        fold_starting_balance = current_compounded_balance
        
        # Evaluate dynamically per asset
        current_idx = 0
        assets_in_test = test_df['asset'].unique()
        
        for asset in assets_in_test:
            asset_test_df = test_df[test_df['asset'] == asset]
            asset_probs = pytorch_probs[current_idx:current_idx + len(asset_test_df)]
            returns_arr = asset_test_df['forward_return'].values
            atr_pct_arr = asset_test_df['ATR_pct'].values
            
            in_position = False
            exit_index = 0
            
            for i in range(len(asset_probs)):
                if in_position and i >= exit_index:
                    in_position = False
                    
                if not in_position and asset_probs[i] >= threshold:
                    trade_gross = returns_arr[i]
                    
                    # 1. REAL-WORLD CAPACITY CONSTRAINT
                    notional_size = current_compounded_balance * LEVERAGE
                    if notional_size > MAX_NOTIONAL_SIZE:
                        notional_size = MAX_NOTIONAL_SIZE
                        
                    # 2. DYNAMIC LIQUIDITY SLIPPAGE (Adds 0.05% slippage per $10k ordered)
                    liquidity_penalty = (notional_size / 10000.0) * 0.0005
                    slippage = 0.001 + (atr_pct_arr[i] * 0.5) + liquidity_penalty
                    
                    # 3. VOLATILITY FILTER
                    if slippage > 0.004:
                        continue
                        
                    in_position = True
                    exit_index = i + horizon
                    
                    # Base net return of the asset
                    base_trade_net = trade_gross - slippage
                    
                    # Actual dollar profit/loss based on the capped notional size
                    dollar_profit = notional_size * base_trade_net
                    current_compounded_balance += dollar_profit
                    
                    if current_compounded_balance < 5.0:
                        current_compounded_balance = 5.0 # Prevent negative balance bug
                    
                    # We still track linear fold metrics using the leveraged multiplier for reporting
                    trade_net = base_trade_net * LEVERAGE
                    fold_gross += trade_gross
                    fold_net += trade_net
                    
                    fold_trades += 1
                    if trade_net > 0:
                        fold_wins += 1
            
            current_idx += len(asset_test_df)
            
        fold_compounded_roi = ((current_compounded_balance - fold_starting_balance) / fold_starting_balance) * 100 if fold_starting_balance > 0 else 0
        print(f"[*] Fold {test_year} | Trades: {fold_trades} | Net P&L (Linear): {fold_net*100:.2f}% | Compounded: {fold_compounded_roi:.2f}% | Win Rate: {(fold_wins/fold_trades*100) if fold_trades>0 else 0:.1f}%")
        
        total_wfo_trades += fold_trades
        total_wfo_gross += fold_gross
        total_wfo_net += fold_net
        total_wfo_wins += fold_wins

    print(f"\n=======================================================")
    print(f" 🏆 TOTAL WALK-FORWARD OPTIMIZATION RESULTS (2022-2026)")
    print(f"=======================================================")
    
    STARTING_BALANCE = 50.00
    
    # Linear Math (Current)
    dollar_profit_linear = STARTING_BALANCE * total_wfo_net
    ending_balance_linear = STARTING_BALANCE + dollar_profit_linear
    
    # Real-World Capped Compounding Math (New)
    ending_balance_compounded = current_compounded_balance
    dollar_profit_compounded = ending_balance_compounded - STARTING_BALANCE
    compounded_roi = ((ending_balance_compounded - STARTING_BALANCE) / STARTING_BALANCE) * 100
    
    win_rate = (total_wfo_wins / total_wfo_trades) * 100 if total_wfo_trades > 0 else 0.0
    
    print(f"--- PyTorch LSTM (WFO + Dynamic Slippage) ---")
    print(f"Total Trades:    {total_wfo_trades}")
    print(f"Win Rate:        {win_rate:.2f}%\n")
    
    print(f"[LINEAR - No Reinvestment]")
    print(f"Net P&L (%):     {total_wfo_net * 100:.2f}%")
    print(f"Ending Bal:      ${ending_balance_linear:.2f} (Profit: ${dollar_profit_linear:.2f})\n")
    
    print(f"[COMPOUNDED - Full Reinvestment]")
    print(f"Net P&L (%):     {compounded_roi:.2f}%")
    print(f"Ending Bal:      ${ending_balance_compounded:.2f} (Profit: ${dollar_profit_compounded:.2f})")
    print("------------------------------------------\n")

if __name__ == "__main__":
    run_wfo()
