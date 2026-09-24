import sys
import os
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from benchmark_models import generate_dataset

def run_svm_only():
    print(f"=======================================================")
    print(f"[*] RUNNING SVM EXCLUSIVELY")
    print(f"=======================================================")
    
    try:
        df, feature_cols, horizon, fee = generate_dataset("BTCUSDT")
    except Exception as e:
        print(f"[!] Error: {e}")
        return
    
    print("[*] Splitting 2019-2026 dataset: Train (2019-2024) | Test (2026)...")
    train_df = df[(df.index.year >= 2019) & (df.index.year <= 2024)]
    test_df = df[df.index.year == 2026]
    
    X_train_raw = train_df[feature_cols].values
    X_test_raw = test_df[feature_cols].values
    y_train = train_df['target'].values
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_raw)
    X_test_scaled = scaler.transform(X_test_raw)
    
    print("[*] Training Linear SVM (Scaled)...")
    svm_model = CalibratedClassifierCV(
        LinearSVC(class_weight='balanced', max_iter=2000, random_state=42), cv=3
    )
    svm_model.fit(X_train_scaled, y_train)
    raw_preds = svm_model.predict_proba(X_test_scaled)
    probs = raw_preds[:, 1]
    
    print("\n=======================================================")
    print(" SVM RESULTS (OOS 2026)")
    print("=======================================================\n")
    
    threshold = 0.42
    in_position = False
    exit_index = 0
    gross_return = 0.0
    net_return = 0.0
    num_trades = 0
    winning_trades = 0
    returns_arr = test_df['forward_return'].values
    
    for i in range(len(probs)):
        if in_position and i >= exit_index:
            in_position = False
            
        if not in_position and probs[i] >= threshold:
            in_position = True
            exit_index = i + horizon
            trade_gross = returns_arr[i]
            trade_net = trade_gross - fee
            gross_return += trade_gross
            net_return += trade_net
            num_trades += 1
            if trade_gross > fee:
                winning_trades += 1
                
    STARTING_BALANCE = 50.00
    dollar_profit = STARTING_BALANCE * net_return
    ending_balance = STARTING_BALANCE + dollar_profit
    
    print(f"--- Linear SVM (Scaled) ---")
    print(f"Threshold:       {threshold * 100}%")
    print(f"Trades:          {num_trades}")
    print(f"Gross P&L (%):   {gross_return * 100:.2f}%")
    print(f"Net P&L (%):     {net_return * 100:.2f}% (After {fee*100}% fee)")
    print(f"Starting Bal:    ${STARTING_BALANCE:.2f}")
    print(f"Ending Bal:      ${ending_balance:.2f} (Profit: ${dollar_profit:.2f})")
    if num_trades > 0:
        print(f"Win Rate:        {(winning_trades / num_trades) * 100:.2f}%")
    print("-------------------------------------------------------\n")

if __name__ == "__main__":
    run_svm_only()
