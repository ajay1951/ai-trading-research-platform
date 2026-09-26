"""
Quantitative Model Benchmark Suite
==================================
Empirical, zero-leakage benchmark comparison across:
1. Buy & Hold
2. Random Signal Baseline
3. Moving Average Strategy (20/50 SMA Crossover)
4. Logistic Regression
5. Random Forest Classifier
6. LightGBM Gradient Boosting
7. PyTorch LSTM
8. Transformer Self-Attention

All models are trained strictly on the chronological Train fold and evaluated
on the identical Out-Of-Sample Test fold with 0.04% transaction fees and 0.02% slippage.
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from lightgbm import LGBMClassifier

from data.splitting import TemporalSplitter
from features.technical import TechnicalFeaturePipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BenchmarkSuite")


# ==============================================================================
# PyTorch Deep Models: LSTM & Minimal Transformer
# ==============================================================================

class PyTorchLSTM(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 64, num_layers: int = 2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2)
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 2)
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


class PyTorchTransformer(nn.Module):
    def __init__(self, input_dim: int, d_model: int = 64, nhead: int = 4, num_layers: int = 2):
        super().__init__()
        self.embedding = nn.Linear(input_dim, d_model)
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, dim_feedforward=128, dropout=0.2, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.fc = nn.Sequential(
            nn.Linear(d_model, 32),
            nn.ReLU(),
            nn.Linear(32, 2)
        )

    def forward(self, x):
        emb = self.embedding(x)
        out = self.transformer(emb)
        return self.fc(out[:, -1, :])


# ==============================================================================
# Simulation & Performance Metrics Engine
# ==============================================================================

def simulate_strategy_returns(
    prices: np.ndarray,
    signals: np.ndarray,
    fee_rate: float = 0.0004,
    slippage: float = 0.0002
) -> Dict[str, Any]:
    """
    Simulates portfolio equity curve from discrete signals (1=Long, 0=Cash/Neutral, -1=Short).
    Applies round-trip transaction costs and slippage on state changes.
    """
    n = len(prices)
    if n < 2 or len(signals) != n:
        return {"return_pct": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "trades": 0, "win_rate": 0.0, "profit_factor": 0.0}

    cost_per_trade = fee_rate + slippage
    pnl_history = []
    trade_returns = []
    current_pos = 0.0
    entry_price = 0.0
    equity = 1.0
    equity_curve = [1.0]

    for t in range(n - 1):
        target_pos = signals[t]
        p_now = prices[t]
        p_next = prices[t + 1]

        # Position change -> incur transaction cost
        if target_pos != current_pos:
            trade_cost = abs(target_pos - current_pos) * cost_per_trade
            equity -= trade_cost
            if current_pos != 0.0 and entry_price > 0.0:
                ret = (p_now - entry_price) / entry_price if current_pos > 0 else (entry_price - p_now) / entry_price
                trade_returns.append(ret)
            current_pos = target_pos
            entry_price = p_now

        # Position step return
        if current_pos != 0.0:
            step_ret = (p_next - p_now) / p_now * current_pos
            equity *= (1.0 + step_ret)

        equity_curve.append(equity)
        pnl_history.append((equity_curve[-1] / equity_curve[-2]) - 1.0 if len(equity_curve) > 1 else 0.0)

    # If position still open at end, close it
    if current_pos != 0.0 and entry_price > 0.0:
        ret = (prices[-1] - entry_price) / entry_price if current_pos > 0 else (entry_price - prices[-1]) / entry_price
        trade_returns.append(ret)

    equity_series = pd.Series(equity_curve)
    ret_series = pd.Series(pnl_history)

    # Metrics
    total_return_pct = (equity_curve[-1] - 1.0) * 100.0
    
    # Annualized Sharpe (assuming 1h bars: 8760 periods/yr)
    mean_ret = ret_series.mean()
    std_ret = ret_series.std()
    sharpe = float((mean_ret / (std_ret + 1e-9)) * np.sqrt(8760)) if std_ret > 0 else 0.0

    # Sortino (downside deviation)
    downside_ret = ret_series[ret_series < 0]
    downside_std = downside_ret.std()
    sortino = float((mean_ret / (downside_std + 1e-9)) * np.sqrt(8760)) if downside_std > 0 else 0.0

    # Max Drawdown
    cum_max = equity_series.cummax()
    drawdown = (equity_series - cum_max) / cum_max
    max_dd_pct = float(abs(drawdown.min()) * 100.0)

    # Calmar Ratio
    calmar = float((total_return_pct / max_dd_pct)) if max_dd_pct > 0 else 0.0

    # Trade stats
    trades_count = len(trade_returns)
    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r <= 0]
    win_rate = (len(wins) / trades_count * 100.0) if trades_count > 0 else 0.0
    gross_profits = sum(wins) if wins else 0.0
    gross_losses = abs(sum(losses)) if losses else 0.0
    profit_factor = float(gross_profits / (gross_losses + 1e-9)) if gross_losses > 0 else (99.0 if gross_profits > 0 else 0.0)

    return {
        "return_pct": round(total_return_pct, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "max_drawdown": round(max_dd_pct, 2),
        "calmar": round(calmar, 2),
        "trades": trades_count,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2)
    }


# ==============================================================================
# Model Benchmark Runner
# ==============================================================================

class ModelBenchmarkSuite:
    def __init__(self, data_path: str = "data/BTCUSDT_1h_historical.csv", sample_bars: int = 15000):
        self.data_path = data_path
        self.sample_bars = sample_bars

    def run(self) -> pd.DataFrame:
        logger.info(f"Loading dataset: {self.data_path}")
        df_raw = pd.read_csv(self.data_path)
        
        # Standardize timestamp
        ts_col = 'timestamp' if 'timestamp' in df_raw.columns else df_raw.columns[0]
        df_raw['timestamp'] = pd.to_datetime(df_raw[ts_col], utc=True, format='mixed')
        df_raw = df_raw.sort_values('timestamp').tail(self.sample_bars).reset_index(drop=True)

        logger.info(f"Extracting causal technical features ({len(df_raw)} bars)...")
        pipeline = TechnicalFeaturePipeline()
        features_df = pipeline.transform(df_raw, dropna=False)

        # Target definition: Binary direction of next 4-hour return (to allow trends to materialize)
        # y_t = 1 if Close[t+4] > Close[t] else 0
        forward_horizon = 4
        forward_return = (df_raw['close'].shift(-forward_horizon) - df_raw['close']) / df_raw['close']
        target = (forward_return > 0.002).astype(int) # Filter micro-noise threshold

        # Combine and align
        dataset = pd.concat([df_raw[['timestamp', 'open', 'high', 'low', 'close', 'volume']], features_df], axis=1)
        dataset['target'] = target

        # Drop initial lookback NaNs and final forward horizon NaNs
        dataset = dataset.dropna().reset_index(drop=True)
        feature_cols = [c for c in features_df.columns if c in dataset.columns]
        logger.info(f"Dataset prepared: {len(dataset)} bars, {len(feature_cols)} features.")

        # Temporal Split: 70% Train, 15% Val, 15% Out-Of-Sample Test with 24-bar embargo
        train_df, val_df, test_df = TemporalSplitter.chronological_split(
            dataset, train_pct=0.70, val_pct=0.15, test_pct=0.15, embargo_bars=24
        )

        logger.info(f"Temporal Split: Train={len(train_df)} | Val={len(val_df)} | Test={len(test_df)}")

        X_train = train_df[feature_cols].values
        y_train = train_df['target'].values
        X_test = test_df[feature_cols].values
        y_test = test_df['target'].values
        test_prices = test_df['close'].values

        # Strict Standardizer: fit ONLY on X_train
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        results = []

        # 1. Buy & Hold Benchmark
        bnh_signals = np.ones(len(test_prices))
        bnh_res = simulate_strategy_returns(test_prices, bnh_signals)
        bnh_res["model"] = "Buy & Hold"
        results.append(bnh_res)

        # 2. Random Baseline (Uniform Random Long/Neutral)
        np.random.seed(42)
        random_signals = np.random.choice([0.0, 1.0], size=len(test_prices), p=[0.5, 0.5])
        rnd_res = simulate_strategy_returns(test_prices, random_signals)
        rnd_res["model"] = "Random Baseline"
        results.append(rnd_res)

        # 3. Moving Average Crossover (20 SMA vs 50 SMA)
        close_series = test_df['close']
        sma_20 = close_series.rolling(20).mean()
        sma_50 = close_series.rolling(50).mean()
        ma_signals = np.where(sma_20 > sma_50, 1.0, 0.0)
        ma_res = simulate_strategy_returns(test_prices, ma_signals)
        ma_res["model"] = "Moving Average (20/50)"
        results.append(ma_res)

        # 4. Logistic Regression
        logger.info("Training Logistic Regression...")
        lr = LogisticRegression(max_iter=1000, random_state=42)
        lr.fit(X_train_scaled, y_train)
        lr_probs = lr.predict_proba(X_test_scaled)[:, 1]
        lr_signals = np.where(lr_probs > 0.52, 1.0, 0.0)
        lr_res = simulate_strategy_returns(test_prices, lr_signals)
        lr_res["model"] = "Logistic Regression"
        results.append(lr_res)

        # 5. Random Forest Classifier
        logger.info("Training Random Forest...")
        rf = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42, n_jobs=-1)
        rf.fit(X_train_scaled, y_train)
        rf_probs = rf.predict_proba(X_test_scaled)[:, 1]
        rf_signals = np.where(rf_probs > 0.52, 1.0, 0.0)
        rf_res = simulate_strategy_returns(test_prices, rf_signals)
        rf_res["model"] = "Random Forest"
        results.append(rf_res)

        # 6. LightGBM Classifier
        logger.info("Training LightGBM...")
        lgb = LGBMClassifier(n_estimators=150, max_depth=5, learning_rate=0.03, random_state=42, verbose=-1)
        lgb.fit(X_train_scaled, y_train)
        lgb_probs = lgb.predict_proba(X_test_scaled)[:, 1]
        lgb_signals = np.where(lgb_probs > 0.52, 1.0, 0.0)
        lgb_res = simulate_strategy_returns(test_prices, lgb_signals)
        lgb_res["model"] = "LightGBM"
        results.append(lgb_res)

        # 7. PyTorch LSTM
        logger.info("Training PyTorch LSTM...")
        lstm_res = self._train_and_eval_pytorch_model(
            model_type="lstm",
            X_train=X_train_scaled,
            y_train=y_train,
            X_test=X_test_scaled,
            test_prices=test_prices,
            seq_len=24
        )
        lstm_res["model"] = "PyTorch LSTM"
        results.append(lstm_res)

        # 8. PyTorch Transformer
        logger.info("Training PyTorch Transformer...")
        trans_res = self._train_and_eval_pytorch_model(
            model_type="transformer",
            X_train=X_train_scaled,
            y_train=y_train,
            X_test=X_test_scaled,
            test_prices=test_prices,
            seq_len=24
        )
        trans_res["model"] = "Transformer (Attention)"
        results.append(trans_res)

        # Format comparison table
        report_df = pd.DataFrame(results)[
            ["model", "return_pct", "sharpe", "sortino", "max_drawdown", "calmar", "trades", "win_rate", "profit_factor"]
        ]
        report_df.columns = ["Model", "Return (%)", "Sharpe", "Sortino", "Max DD (%)", "Calmar", "Trades", "Win Rate (%)", "Profit Factor"]
        report_df = report_df.sort_values(by="Sharpe", ascending=False).reset_index(drop=True)

        return report_df

    def _train_and_eval_pytorch_model(
        self,
        model_type: str,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        test_prices: np.ndarray,
        seq_len: int = 24
    ) -> Dict[str, Any]:
        """Trains PyTorch LSTM or Transformer and evaluates on test slice."""
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        input_dim = X_train.shape[1]

        # Prepare 3D sequential sliding windows
        def make_sequences(X, y, seq_l):
            Xs, ys = [], []
            for i in range(len(X) - seq_l):
                Xs.append(X[i : i + seq_l])
                ys.append(y[i + seq_l])
            return np.array(Xs), np.array(ys)

        X_tr_seq, y_tr_seq = make_sequences(X_train, y_train, seq_len)
        X_te_seq, _ = make_sequences(X_test, np.zeros(len(X_test)), seq_len)

        if model_type == "lstm":
            model = PyTorchLSTM(input_dim=input_dim, hidden_dim=48, num_layers=2).to(device)
        else:
            model = PyTorchTransformer(input_dim=input_dim, d_model=48, nhead=4, num_layers=2).to(device)

        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)

        # Fast training (10 epochs for benchmark)
        dataset_tr = torch.utils.data.TensorDataset(
            torch.tensor(X_tr_seq, dtype=torch.float32),
            torch.tensor(y_tr_seq, dtype=torch.long)
        )
        loader = torch.utils.data.DataLoader(dataset_tr, batch_size=128, shuffle=True)

        model.train()
        for epoch in range(8):
            for bx, by in loader:
                bx, by = bx.to(device), by.to(device)
                optimizer.zero_grad()
                out = model(bx)
                loss = criterion(out, by)
                loss.backward()
                optimizer.step()

        # Inference on test set
        model.eval()
        with torch.no_grad():
            te_tensor = torch.tensor(X_te_seq, dtype=torch.float32).to(device)
            logits = model(te_tensor)
            probs = torch.softmax(logits, dim=-1)[:, 1].cpu().numpy()

        # Pad initial seq_len bars with 0.0 signal
        full_signals = np.zeros(len(test_prices))
        raw_signals = np.where(probs > 0.52, 1.0, 0.0)
        full_signals[seq_len : seq_len + len(raw_signals)] = raw_signals

        return simulate_strategy_returns(test_prices, full_signals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quantitative Model Benchmark Suite")
    parser.add_argument("--data", type=str, default="data/BTCUSDT_1h_historical.csv", help="Path to OHLCV dataset")
    parser.add_argument("--bars", type=int, default=15000, help="Number of recent bars to evaluate (default 15000 = ~1.7 years)")
    parser.add_argument("--out", type=str, default="docs/benchmark_results.json", help="Path to save benchmark JSON results")
    args = parser.parse_args()

    suite = ModelBenchmarkSuite(data_path=args.data, sample_bars=args.bars)
    results_df = suite.run()

    print("\n" + "=" * 90)
    print("      OUT-OF-SAMPLE MODEL BENCHMARK RESULTS (0.04% Fees + 0.02% Slippage)")
    print("=" * 90)
    print(results_df.to_markdown(index=False))
    print("=" * 90 + "\n")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        results_df.to_json(args.out, orient="records", indent=2)
        print(f"[+] Benchmark results saved to {args.out}")
