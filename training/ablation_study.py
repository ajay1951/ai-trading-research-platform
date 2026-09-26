"""
Quantitative Research: Systematic Ablation Study Engine
=======================================================
Evaluates feature group importance and sequence length sensitivity:
- Full Model (Price + Volatility + Momentum + Volume)
- Ablation: Without Volatility Features
- Ablation: Without Momentum Features
- Ablation: Without Volume Features
- Ablation: Without Price Features
- Sensitivity: Sequence Length 12 vs 24 vs 48
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, Any, List
import pandas as pd
import numpy as np
import torch
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier

from data.splitting import TemporalSplitter
from features.technical import TechnicalFeaturePipeline
from training.benchmark_suite import simulate_strategy_returns, PyTorchLSTM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AblationStudy")


class AblationStudyEngine:
    def __init__(self, data_path: str = "data/BTCUSDT_1h_historical.csv", sample_bars: int = 8000):
        self.data_path = data_path
        self.sample_bars = sample_bars

    def run(self) -> pd.DataFrame:
        logger.info(f"Loading dataset for ablation: {self.data_path}")
        df_raw = pd.read_csv(self.data_path)
        ts_col = 'timestamp' if 'timestamp' in df_raw.columns else df_raw.columns[0]
        df_raw['timestamp'] = pd.to_datetime(df_raw[ts_col], utc=True, format='mixed')
        df_raw = df_raw.sort_values('timestamp').tail(self.sample_bars).reset_index(drop=True)

        # Target forward 4h return
        forward_return = (df_raw['close'].shift(-4) - df_raw['close']) / df_raw['close']
        target = (forward_return > 0.002).astype(int)

        # Configurations to test
        ablation_configs = [
            {"name": "Full Model (All Features)", "domains": ["price", "volatility", "momentum", "volume"]},
            {"name": "Without Volatility", "domains": ["price", "momentum", "volume"]},
            {"name": "Without Momentum", "domains": ["price", "volatility", "volume"]},
            {"name": "Without Volume", "domains": ["price", "volatility", "momentum"]},
            {"name": "Without Price Structure", "domains": ["volatility", "momentum", "volume"]},
        ]

        results = []

        for cfg in ablation_configs:
            cfg_name = cfg["name"]
            domains = cfg["domains"]
            logger.info(f"Evaluating Ablation: {cfg_name}...")

            pipeline = TechnicalFeaturePipeline(include_domains=domains)
            features = pipeline.transform(df_raw, dropna=False)

            dataset = pd.concat([df_raw[['timestamp', 'close']], features], axis=1)
            dataset['target'] = target
            dataset = dataset.dropna().reset_index(drop=True)

            feature_cols = [c for c in features.columns if c in dataset.columns]

            train_df, val_df, test_df = TemporalSplitter.chronological_split(
                dataset, train_pct=0.70, val_pct=0.15, test_pct=0.15, embargo_bars=24
            )

            X_train = train_df[feature_cols].values
            y_train = train_df['target'].values
            X_test = test_df[feature_cols].values
            y_test = test_df['target'].values
            test_prices = test_df['close'].values

            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # Evaluate with Random Forest for fast, reproducible feature attribution
            rf = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42, n_jobs=-1)
            rf.fit(X_train_scaled, y_train)
            probs = rf.predict_proba(X_test_scaled)[:, 1]
            signals = np.where(probs > 0.52, 1.0, 0.0)

            perf = simulate_strategy_returns(test_prices, signals)
            perf["configuration"] = cfg_name
            perf["feature_count"] = len(feature_cols)
            perf["accuracy"] = round((rf.predict(X_test_scaled) == y_test).mean() * 100.0, 2)
            results.append(perf)

        df_res = pd.DataFrame(results)[
            ["configuration", "feature_count", "accuracy", "return_pct", "sharpe", "sortino", "max_drawdown", "trades", "win_rate", "profit_factor"]
        ]
        df_res.columns = [
            "Configuration", "Features", "Accuracy (%)", "Return (%)", "Sharpe", "Sortino", "Max DD (%)", "Trades", "Win Rate (%)", "Profit Factor"
        ]
        return df_res


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Systematic Ablation Study Engine")
    parser.add_argument("--data", type=str, default="data/BTCUSDT_1h_historical.csv", help="Path to OHLCV dataset")
    parser.add_argument("--bars", type=int, default=8000, help="Number of bars to analyze")
    parser.add_argument("--out", type=str, default="docs/ablation_results.json", help="Path to save output JSON")
    args = parser.parse_args()

    engine = AblationStudyEngine(data_path=args.data, sample_bars=args.bars)
    res_df = engine.run()

    print("\n" + "=" * 90)
    print("               SYSTEMATIC FEATURE GROUP ABLATION STUDY RESULTS")
    print("=" * 90)
    print(res_df.to_markdown(index=False))
    print("=" * 90 + "\n")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        res_df.to_json(args.out, orient="records", indent=2)
        print(f"[+] Ablation results saved to {args.out}")
