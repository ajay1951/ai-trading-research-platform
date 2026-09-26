"""
Multi-Asset Quantitative Universe Benchmark Engine
==================================================
Runs cross-asset benchmark evaluations across all 13 high-liquidity cryptocurrency assets:
BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, NEAR, LTC, DOT, SUI.

All models are trained strictly on chronological In-Sample slices and evaluated
on the identical Out-Of-Sample test slice with 0.04% fees and 0.02% slippage.
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from lightgbm import LGBMClassifier

from data.validator import OHLCVValidator
from data.splitting import TemporalSplitter
from features.technical import TechnicalFeaturePipeline
from training.benchmark_suite import simulate_strategy_returns

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("UniverseBenchmark")

UNIVERSE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
    "LTCUSDT", "DOTUSDT", "SUIUSDT"
]


class UniverseBenchmarkRunner:
    def __init__(self, data_dir: str = "data", sample_bars: int = 5000):
        self.data_dir = data_dir
        self.sample_bars = sample_bars
        self.validator = OHLCVValidator(timeframe="1h")
        self.feature_pipeline = TechnicalFeaturePipeline()

    def evaluate_asset(self, symbol: str) -> List[Dict[str, Any]]:
        csv_file = os.path.join(self.data_dir, f"{symbol}_1h_historical.csv")
        if not os.path.exists(csv_file):
            logger.warning(f"File not found for {symbol}: {csv_file}")
            return []

        df_raw = pd.read_csv(csv_file)
        ts_col = 'timestamp' if 'timestamp' in df_raw.columns else df_raw.columns[0]
        df_raw['timestamp'] = pd.to_datetime(df_raw[ts_col], utc=True, format='mixed')
        df_raw = df_raw.sort_values('timestamp').tail(self.sample_bars).reset_index(drop=True)

        if len(df_raw) < 500:
            logger.warning(f"Insufficient bars for {symbol} ({len(df_raw)} bars)")
            return []

        # Extract causal features
        features = self.feature_pipeline.transform(df_raw, dropna=False)

        # 4-hour forward target
        forward_return = (df_raw['close'].shift(-4) - df_raw['close']) / df_raw['close']
        target = (forward_return > 0.002).astype(int)

        dataset = pd.concat([df_raw[['timestamp', 'close']], features], axis=1)
        dataset['target'] = target
        dataset = dataset.dropna().reset_index(drop=True)

        feature_cols = [c for c in features.columns if c in dataset.columns]

        # Chronological split: 70% Train, 15% Val, 15% Test with 24-bar embargo
        train_df, val_df, test_df = TemporalSplitter.chronological_split(
            dataset, train_pct=0.70, val_pct=0.15, test_pct=0.15, embargo_bars=24
        )

        X_train = train_df[feature_cols].values
        y_train = train_df['target'].values
        X_test = test_df[feature_cols].values
        test_prices = test_df['close'].values

        # Scale strictly on train
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        records = []

        # 1. Buy & Hold
        bnh_signals = np.ones(len(test_prices))
        bnh_res = simulate_strategy_returns(test_prices, bnh_signals)
        bnh_res.update({"symbol": symbol, "model": "Buy & Hold", "test_bars": len(test_prices)})
        records.append(bnh_res)

        # 2. Moving Average (20/50 SMA)
        close_series = test_df['close']
        ma_signals = np.where(close_series.rolling(20).mean() > close_series.rolling(50).mean(), 1.0, 0.0)
        ma_res = simulate_strategy_returns(test_prices, ma_signals)
        ma_res.update({"symbol": symbol, "model": "Moving Average (20/50)", "test_bars": len(test_prices)})
        records.append(ma_res)

        # 3. Random Forest (100 Trees)
        rf = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42, n_jobs=-1)
        rf.fit(X_train_scaled, y_train)
        rf_probs = rf.predict_proba(X_test_scaled)[:, 1]
        rf_signals = np.where(rf_probs > 0.52, 1.0, 0.0)
        rf_res = simulate_strategy_returns(test_prices, rf_signals)
        rf_res.update({"symbol": symbol, "model": "Random Forest", "test_bars": len(test_prices)})
        records.append(rf_res)

        # 4. LightGBM
        lgb = LGBMClassifier(n_estimators=120, max_depth=5, learning_rate=0.03, random_state=42, verbose=-1)
        lgb.fit(X_train_scaled, y_train)
        lgb_probs = lgb.predict_proba(X_test_scaled)[:, 1]
        lgb_signals = np.where(lgb_probs > 0.52, 1.0, 0.0)
        lgb_res = simulate_strategy_returns(test_prices, lgb_signals)
        lgb_res.update({"symbol": symbol, "model": "LightGBM", "test_bars": len(test_prices)})
        records.append(lgb_res)

        return records

    def run_universe(self, symbols: List[str] = UNIVERSE_SYMBOLS) -> pd.DataFrame:
        all_results = []
        for sym in symbols:
            logger.info(f"Benchmarking universe asset: {sym}...")
            res = self.evaluate_asset(sym)
            all_results.extend(res)

        df = pd.DataFrame(all_results)[
            ["symbol", "model", "return_pct", "sharpe", "sortino", "max_drawdown", "trades", "win_rate", "profit_factor"]
        ]
        df.columns = [
            "Asset", "Model", "Return (%)", "Sharpe", "Sortino", "Max DD (%)", "Trades", "Win Rate (%)", "Profit Factor"
        ]
        return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Asset Universe Benchmark Runner")
    parser.add_argument("--bars", type=int, default=5000, help="Recent bars per asset")
    parser.add_argument("--out", type=str, default="docs/universe_benchmark_results.json")
    args = parser.parse_args()

    runner = UniverseBenchmarkRunner(sample_bars=args.bars)
    results_df = runner.run_universe()

    print("\n" + "=" * 95)
    print("        13-ASSET MULTI-ASSET QUANTITATIVE UNIVERSE BENCHMARK RESULTS")
    print("=" * 95)
    print(results_df.to_markdown(index=False))
    print("=" * 95 + "\n")

    # Aggregate by model across all 13 assets
    agg_df = results_df.groupby("Model").agg({
        "Return (%)": "mean",
        "Sharpe": "mean",
        "Max DD (%)": "mean",
        "Trades": "sum",
        "Win Rate (%)": "mean",
        "Profit Factor": "mean"
    }).round(2).reset_index()
    agg_df = agg_df.sort_values(by="Sharpe", ascending=False)

    print("\n" + "=" * 80)
    print("           PORTFOLIO-AGGREGATED PERFORMANCE ACROSS 13 ASSETS")
    print("=" * 80)
    print(agg_df.to_markdown(index=False))
    print("=" * 80 + "\n")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        results_df.to_json(args.out, orient="records", indent=2)
        md_path = args.out.replace(".json", ".md")
        with open(md_path, "w") as f:
            f.write("# 13-Asset Universe Benchmark Results\n\n")
            f.write(results_df.to_markdown(index=False))
            f.write("\n\n## Aggregated Portfolio Metrics\n\n")
            f.write(agg_df.to_markdown(index=False))
        print(f"[+] Multi-asset universe results saved to {args.out} and {md_path}")
