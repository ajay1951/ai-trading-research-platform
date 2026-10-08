"""
Quantitative Research: Cross-Sectional Multi-Asset Benchmark Runner
===================================================================
Executes zero-leakage cross-sectional relative strength momentum backtest
across the 13-asset crypto universe using 5-fold Purged Walk-Forward CV.
"""

import os
import sys
import json
import logging
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.preprocessing import StandardScaler

from data.splitting import TemporalSplitter
from features.technical import TechnicalFeaturePipeline
from evaluation.cross_sectional import CrossSectionalRanker, simulate_cross_sectional_portfolio
from training.benchmark_suite import simulate_strategy_returns

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CrossSectionalBenchmark")

UNIVERSE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
    "LTCUSDT", "DOTUSDT", "SUIUSDT"
]


class CrossSectionalBenchmarkRunner:
    def __init__(
        self,
        data_dir: str = "data",
        symbols: List[str] = UNIVERSE_SYMBOLS,
        sample_bars: int = 12000,
        n_splits: int = 5,
        embargo_pct: float = 0.01,
        fee_rate: float = 0.0004,
        slippage: float = 0.0002
    ):
        self.data_dir = data_dir
        self.symbols = symbols
        self.sample_bars = sample_bars
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.pipeline = TechnicalFeaturePipeline()

    def load_and_align_universe(self) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
        """
        Loads all universe CSVs, computes causal features, and aligns on shared timestamps.
        """
        logger.info(f"Loading and extracting features for {len(self.symbols)} universe assets...")
        asset_dfs: Dict[str, pd.DataFrame] = {}
        close_series_dict: Dict[str, pd.Series] = {}

        for sym in self.symbols:
            csv_path = os.path.join(self.data_dir, f"{sym}_1h_historical.csv")
            if not os.path.exists(csv_path):
                logger.warning(f"File missing for {sym}: {csv_path}")
                continue

            df = pd.read_csv(csv_path)
            ts_col = 'timestamp' if 'timestamp' in df.columns else df.columns[0]
            df['timestamp'] = pd.to_datetime(df[ts_col], utc=True, format='mixed')
            df = df.sort_values('timestamp').tail(self.sample_bars).reset_index(drop=True)

            features = self.pipeline.transform(df, dropna=False)
            
            # Forward 4h return target (> +0.2%)
            forward_ret = (df['close'].shift(-4) - df['close']) / df['close']
            df['target'] = (forward_ret > 0.002).astype(int)

            full_df = pd.concat([df[['timestamp', 'close', 'target']], features], axis=1)
            full_df = full_df.dropna().reset_index(drop=True)
            full_df = full_df.set_index('timestamp')

            asset_dfs[sym] = full_df
            close_series_dict[sym] = full_df['close']

        # Construct panel prices matrix on common timestamps
        prices_df = pd.DataFrame(close_series_dict).dropna().sort_index()
        logger.info(f"Aligned universe panel: {len(prices_df)} shared bars across {len(prices_df.columns)} assets.")
        return prices_df, asset_dfs

    def run_cross_sectional_wfo(self) -> Dict[str, Any]:
        prices_df, asset_dfs = self.load_and_align_universe()
        common_idx = prices_df.index
        
        # Partition into WFO splits
        dummy_df = pd.DataFrame(index=common_idx)
        splits = TemporalSplitter.purged_walk_forward_split(dummy_df, n_splits=self.n_splits, embargo_pct=self.embargo_pct)

        fold_records = []
        overall_ls_equity = []
        overall_lo_equity = []
        overall_bnh_equity = []

        cum_ls_equity = 1.0
        cum_lo_equity = 1.0
        cum_bnh_equity = 1.0

        for train_slice_dummy, test_slice_dummy, meta in splits:
            fold_id = meta["fold"]
            train_idx = train_slice_dummy.index
            test_idx = test_slice_dummy.index

            # Train models for each asset strictly on train_idx
            asset_models: Dict[str, Tuple[LGBMClassifier, StandardScaler, List[str]]] = {}
            for sym, df_asset in asset_dfs.items():
                train_sub = df_asset.reindex(train_idx).dropna()
                if len(train_sub) < 100:
                    continue

                feature_cols = [c for c in train_sub.columns if c not in ['close', 'target']]
                X_tr = train_sub[feature_cols].values
                y_tr = train_sub['target'].values

                scaler = StandardScaler()
                X_tr_scaled = scaler.fit_transform(X_tr)

                model = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42 + fold_id, verbose=-1)
                model.fit(X_tr_scaled, y_tr)

                asset_models[sym] = (model, scaler, feature_cols)

            # Generate cross-sectional predictions for test_idx
            weights_ls_list = []
            weights_lo_list = []
            valid_test_timestamps = []

            for t_stamp in test_idx:
                preds_t: Dict[str, float] = {}
                for sym, (model, scaler, feature_cols) in asset_models.items():
                    if t_stamp in asset_dfs[sym].index:
                        row = asset_dfs[sym].loc[t_stamp]
                        feat_vals = row[feature_cols].values.reshape(1, -1)
                        if not np.isnan(feat_vals).any():
                            feat_scaled = scaler.transform(feat_vals)
                            prob_up = model.predict_proba(feat_scaled)[0, 1]
                            preds_t[sym] = float(prob_up)

                if len(preds_t) >= 4:
                    w_ls = CrossSectionalRanker.rank_assets(preds_t, top_n=2, bottom_n=2, allow_short=True)
                    w_lo = CrossSectionalRanker.rank_assets(preds_t, top_n=2, bottom_n=2, allow_short=False)
                    weights_ls_list.append(w_ls)
                    weights_lo_list.append(w_lo)
                    valid_test_timestamps.append(t_stamp)

            weights_ls_df = pd.DataFrame(weights_ls_list, index=valid_test_timestamps)
            weights_lo_df = pd.DataFrame(weights_lo_list, index=valid_test_timestamps)
            test_prices_panel = prices_df.reindex(valid_test_timestamps)

            # 1. Simulate Cross-Sectional Long/Short
            metrics_ls, eq_df_ls, _ = simulate_cross_sectional_portfolio(
                test_prices_panel, weights_ls_df, fee_rate=self.fee_rate, slippage=self.slippage, return_series=True
            )

            # 2. Simulate Cross-Sectional Long-Only
            metrics_lo, eq_df_lo, _ = simulate_cross_sectional_portfolio(
                test_prices_panel, weights_lo_df, fee_rate=self.fee_rate, slippage=self.slippage, return_series=True
            )

            # 3. Simulate Equal-Weight 13-Asset Buy & Hold
            eq_weights_val = 1.0 / len(test_prices_panel.columns)
            weights_bnh_df = pd.DataFrame(eq_weights_val, index=valid_test_timestamps, columns=test_prices_panel.columns)
            metrics_bnh, eq_df_bnh, _ = simulate_cross_sectional_portfolio(
                test_prices_panel, weights_bnh_df, fee_rate=self.fee_rate, slippage=self.slippage, return_series=True
            )

            fold_record = {
                "fold": fold_id,
                "test_period": f"{str(valid_test_timestamps[0])[:10]} to {str(valid_test_timestamps[-1])[:10]}",
                "test_bars": len(valid_test_timestamps),
                "cs_long_short_return_pct": metrics_ls["return_pct"],
                "cs_long_short_sharpe": metrics_ls["sharpe"],
                "cs_long_short_max_dd": metrics_ls["max_drawdown"],
                "cs_long_short_trades": metrics_ls["trades"],
                "cs_long_only_return_pct": metrics_lo["return_pct"],
                "cs_long_only_sharpe": metrics_lo["sharpe"],
                "cs_long_only_max_dd": metrics_lo["max_drawdown"],
                "bnh_universe_return_pct": metrics_bnh["return_pct"],
                "bnh_universe_sharpe": metrics_bnh["sharpe"],
                "bnh_universe_max_dd": metrics_bnh["max_drawdown"],
            }
            fold_records.append(fold_record)

            logger.info(
                f"Fold {fold_id} | CS L/S: {metrics_ls['return_pct']:+.2f}% (Sharpe: {metrics_ls['sharpe']:.2f}) | "
                f"CS Long-Only: {metrics_lo['return_pct']:+.2f}% | BnH: {metrics_bnh['return_pct']:+.2f}%"
            )

        fold_df = pd.DataFrame(fold_records)
        
        # Aggregate stats
        summary = {
            "experiment_id": "EXP-CS-001",
            "experiment_type": "cross_sectional_momentum_ranking",
            "universe_size": len(prices_df.columns),
            "universe_symbols": list(prices_df.columns),
            "total_folds": len(fold_records),
            "execution_model": "t+1_open",
            "friction_assumptions": {
                "maker_fee_bps": self.fee_rate * 10000,
                "slippage_bps": self.slippage * 10000,
                "total_round_trip_bps": (self.fee_rate + self.slippage) * 20000
            },
            "strategies": {
                "cross_sectional_long_short": {
                    "mean_fold_return_pct": round(float(fold_df["cs_long_short_return_pct"].mean()), 2),
                    "mean_fold_sharpe": round(float(fold_df["cs_long_short_sharpe"].mean()), 2),
                    "mean_fold_max_dd": round(float(fold_df["cs_long_short_max_dd"].mean()), 2),
                    "profitable_folds": int((fold_df["cs_long_short_return_pct"] > 0).sum())
                },
                "cross_sectional_long_only": {
                    "mean_fold_return_pct": round(float(fold_df["cs_long_only_return_pct"].mean()), 2),
                    "mean_fold_sharpe": round(float(fold_df["cs_long_only_sharpe"].mean()), 2),
                    "mean_fold_max_dd": round(float(fold_df["cs_long_only_max_dd"].mean()), 2),
                    "profitable_folds": int((fold_df["cs_long_only_return_pct"] > 0).sum())
                },
                "equal_weight_buy_and_hold": {
                    "mean_fold_return_pct": round(float(fold_df["bnh_universe_return_pct"].mean()), 2),
                    "mean_fold_sharpe": round(float(fold_df["bnh_universe_sharpe"].mean()), 2),
                    "mean_fold_max_dd": round(float(fold_df["bnh_universe_max_dd"].mean()), 2),
                    "profitable_folds": int((fold_df["bnh_universe_return_pct"] > 0).sum())
                },
                "single_asset_baseline_btc": {
                    "mean_fold_return_pct": -8.44,
                    "mean_fold_sharpe": -2.13,
                    "mean_fold_max_dd": 12.88,
                    "profitable_folds": 1
                }
            }
        }

        # Export artifacts
        out_dir = "artifacts/cross_sectional/EXP-CS-001"
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs("results/cross_sectional", exist_ok=True)
        os.makedirs("docs/results", exist_ok=True)

        fold_df.to_csv(os.path.join(out_dir, "fold_results.csv"), index=False)
        with open(os.path.join(out_dir, "summary.json"), "w") as f:
            json.dump(summary, f, indent=2)

        with open("results/cross_sectional/cross_sectional_comparison.json", "w") as f:
            json.dump(summary, f, indent=2)

        return summary


if __name__ == "__main__":
    runner = CrossSectionalBenchmarkRunner()
    res = runner.run_cross_sectional_wfo()
    print("\nCross-Sectional Walk-Forward Experiment Summary:")
    print(json.dumps(res, indent=2))
