"""
Quantitative Research: Cross-Sectional Rebalance-Frequency Benchmark Engine (EXP-CS-RB-001)
=============================================================================================
Isolates rebalancing frequency (1h, 4h, 12h, 24h) as the primary independent variable across
both Long-Only (Top 2) and Long/Short (Top 2 / Bottom 2) cross-sectional momentum strategies.
Uses identical models, 13-asset universe, 5-fold WFO, 24-bar embargo, and 12 bps friction.
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RebalanceFrequencyBenchmark")

UNIVERSE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
    "LTCUSDT", "DOTUSDT", "SUIUSDT"
]

REBALANCE_INTERVALS = {
    "1H": 1,
    "4H": 4,
    "12H": 12,
    "24H": 24
}


class RebalanceFrequencyRunner:
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
        logger.info(f"Loading and extracting features for {len(self.symbols)} assets...")
        asset_dfs: Dict[str, pd.DataFrame] = {}
        close_series_dict: Dict[str, pd.Series] = {}

        for sym in self.symbols:
            csv_path = os.path.join(self.data_dir, f"{sym}_1h_historical.csv")
            if not os.path.exists(csv_path):
                continue

            df = pd.read_csv(csv_path)
            ts_col = 'timestamp' if 'timestamp' in df.columns else df.columns[0]
            df['timestamp'] = pd.to_datetime(df[ts_col], utc=True, format='mixed')
            df = df.sort_values('timestamp').tail(self.sample_bars).reset_index(drop=True)

            features = self.pipeline.transform(df, dropna=False)
            forward_ret = (df['close'].shift(-4) - df['close']) / df['close']
            df['target'] = (forward_ret > 0.002).astype(int)

            full_df = pd.concat([df[['timestamp', 'close', 'target']], features], axis=1).dropna().reset_index(drop=True)
            full_df = full_df.set_index('timestamp')

            asset_dfs[sym] = full_df
            close_series_dict[sym] = full_df['close']

        prices_df = pd.DataFrame(close_series_dict).dropna().sort_index()
        return prices_df, asset_dfs

    def run_frequency_sweep(self) -> Dict[str, Any]:
        prices_df, asset_dfs = self.load_and_align_universe()
        common_idx = prices_df.index
        
        dummy_df = pd.DataFrame(index=common_idx)
        splits = TemporalSplitter.purged_walk_forward_split(dummy_df, n_splits=self.n_splits, embargo_pct=self.embargo_pct)

        all_fold_records = []
        rank_persistence_metrics = []

        # Containers for aggregated frequency results
        freq_results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
            freq_name: {"long_only": [], "long_short": []}
            for freq_name in REBALANCE_INTERVALS.keys()
        }

        for train_slice_dummy, test_slice_dummy, meta in splits:
            fold_id = meta["fold"]
            train_idx = train_slice_dummy.index
            test_idx = test_slice_dummy.index

            # Train models on train_idx
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

            # Generate raw hourly predictions matrix on test_idx
            preds_matrix: Dict[str, List[float]] = {sym: [] for sym in asset_models.keys()}
            valid_test_timestamps = []

            for t_stamp in test_idx:
                row_preds = {}
                for sym, (model, scaler, feature_cols) in asset_models.items():
                    if t_stamp in asset_dfs[sym].index:
                        row = asset_dfs[sym].loc[t_stamp]
                        feat_vals = row[feature_cols].values.reshape(1, -1)
                        if not np.isnan(feat_vals).any():
                            feat_scaled = scaler.transform(feat_vals)
                            prob_up = float(model.predict_proba(feat_scaled)[0, 1])
                            row_preds[sym] = prob_up

                if len(row_preds) >= 4:
                    for sym in asset_models.keys():
                        preds_matrix[sym].append(row_preds.get(sym, np.nan))
                    valid_test_timestamps.append(t_stamp)

            preds_df = pd.DataFrame(preds_matrix, index=valid_test_timestamps)
            test_prices_panel = prices_df.reindex(valid_test_timestamps)

            # Measure rank persistence for this fold
            fold_persistence = CrossSectionalRanker.compute_rank_persistence(preds_df, top_n=2, bottom_n=2)
            fold_persistence["fold"] = fold_id
            rank_persistence_metrics.append(fold_persistence)

            # Compute raw hourly target weights
            raw_weights_lo = []
            raw_weights_ls = []
            for t_idx in range(len(preds_df)):
                s_dict = preds_df.iloc[t_idx].dropna().to_dict()
                w_lo = CrossSectionalRanker.rank_assets(s_dict, top_n=2, bottom_n=2, allow_short=False)
                w_ls = CrossSectionalRanker.rank_assets(s_dict, top_n=2, bottom_n=2, allow_short=True)
                raw_weights_lo.append(w_lo)
                raw_weights_ls.append(w_ls)

            raw_weights_lo_df = pd.DataFrame(raw_weights_lo, index=valid_test_timestamps)
            raw_weights_ls_df = pd.DataFrame(raw_weights_ls, index=valid_test_timestamps)

            # Evaluate across rebalance intervals
            for freq_name, interval_bars in REBALANCE_INTERVALS.items():
                w_lo_sched = CrossSectionalRanker.apply_rebalance_frequency(raw_weights_lo_df, interval_bars=interval_bars)
                w_ls_sched = CrossSectionalRanker.apply_rebalance_frequency(raw_weights_ls_df, interval_bars=interval_bars)

                m_lo = simulate_cross_sectional_portfolio(test_prices_panel, w_lo_sched, fee_rate=self.fee_rate, slippage=self.slippage)
                m_ls = simulate_cross_sectional_portfolio(test_prices_panel, w_ls_sched, fee_rate=self.fee_rate, slippage=self.slippage)

                m_lo.update({"fold": fold_id, "frequency": freq_name, "interval_bars": interval_bars, "strategy": "Long-Only"})
                m_ls.update({"fold": fold_id, "frequency": freq_name, "interval_bars": interval_bars, "strategy": "Long/Short"})

                freq_results[freq_name]["long_only"].append(m_lo)
                freq_results[freq_name]["long_short"].append(m_ls)

                all_fold_records.append({
                    "experiment": f"CS-RB-{interval_bars:03d}",
                    "fold": fold_id,
                    "frequency": freq_name,
                    "interval_bars": interval_bars,
                    "test_period": f"{str(valid_test_timestamps[0])[:10]} to {str(valid_test_timestamps[-1])[:10]}",
                    "lo_return_pct": m_lo["return_pct"],
                    "lo_gross_return_pct": m_lo["gross_return_pct"],
                    "lo_costs_pct": m_lo["total_costs_pct"],
                    "lo_sharpe": m_lo["sharpe"],
                    "lo_max_dd": m_lo["max_drawdown"],
                    "lo_daily_turnover": m_lo["turnover"],
                    "lo_avg_hold_hours": m_lo["avg_holding_period_hours"],
                    "ls_return_pct": m_ls["return_pct"],
                    "ls_gross_return_pct": m_ls["gross_return_pct"],
                    "ls_costs_pct": m_ls["total_costs_pct"],
                    "ls_sharpe": m_ls["sharpe"],
                    "ls_max_dd": m_ls["max_drawdown"],
                    "ls_daily_turnover": m_ls["turnover"],
                    "ls_avg_hold_hours": m_ls["avg_holding_period_hours"],
                })

            logger.info(
                f"Fold {fold_id} completed | 1H LO: {freq_results['1H']['long_only'][-1]['return_pct']:+.2f}% | "
                f"24H LO: {freq_results['24H']['long_only'][-1]['return_pct']:+.2f}% | "
                f"1H LS: {freq_results['1H']['long_short'][-1]['return_pct']:+.2f}% | "
                f"24H LS: {freq_results['24H']['long_short'][-1]['return_pct']:+.2f}%"
            )

        fold_df = pd.DataFrame(all_fold_records)
        persistence_df = pd.DataFrame(rank_persistence_metrics)

        # Build aggregated frequency comparison
        comparison_summary = []
        for freq_name, interval_bars in REBALANCE_INTERVALS.items():
            lo_folds = freq_results[freq_name]["long_only"]
            ls_folds = freq_results[freq_name]["long_short"]

            def agg_metrics(fold_list: List[Dict[str, Any]], strat_name: str) -> Dict[str, Any]:
                ret_arr = [f["return_pct"] for f in fold_list]
                gross_arr = [f["gross_return_pct"] for f in fold_list]
                costs_arr = [f["total_costs_pct"] for f in fold_list]
                sharpe_arr = [f["sharpe"] for f in fold_list]
                sortino_arr = [f["sortino"] for f in fold_list]
                dd_arr = [f["max_drawdown"] for f in fold_list]
                turnover_arr = [f["turnover"] for f in fold_list]
                hold_arr = [f["avg_holding_period_hours"] for f in fold_list]
                rebal_arr = [f["rebalances"] for f in fold_list]

                return {
                    "strategy": strat_name,
                    "frequency": freq_name,
                    "interval_bars": interval_bars,
                    "mean_return_pct": round(float(np.mean(ret_arr)), 2),
                    "mean_gross_return_pct": round(float(np.mean(gross_arr)), 2),
                    "mean_costs_pct": round(float(np.mean(costs_arr)), 2),
                    "mean_sharpe": round(float(np.mean(sharpe_arr)), 2),
                    "mean_sortino": round(float(np.mean(sortino_arr)), 2),
                    "mean_max_dd_pct": round(float(np.mean(dd_arr)), 2),
                    "mean_daily_turnover": round(float(np.mean(turnover_arr)), 4),
                    "mean_holding_period_hours": round(float(np.mean(hold_arr)), 2),
                    "mean_rebalances_per_fold": round(float(np.mean(rebal_arr)), 1),
                    "profitable_folds": f"{int((np.array(ret_arr) > 0).sum())}/{len(ret_arr)}"
                }

            comparison_summary.append(agg_metrics(lo_folds, "Cross-Sectional Long-Only (Top 2)"))
            comparison_summary.append(agg_metrics(ls_folds, "Cross-Sectional Long/Short (Top 2 / Bottom 2)"))

        summary_df = pd.DataFrame(comparison_summary)

        # Average persistence across all folds
        avg_persistence = {
            "rank_autocorrelation_1h": round(float(persistence_df["rank_corr_1h"].mean()), 4),
            "rank_autocorrelation_4h": round(float(persistence_df["rank_corr_4h"].mean()), 4),
            "rank_autocorrelation_12h": round(float(persistence_df["rank_corr_12h"].mean()), 4),
            "rank_autocorrelation_24h": round(float(persistence_df["rank_corr_24h"].mean()), 4),
            "top_2_jaccard_overlap_1h": round(float(persistence_df["top_n_persistence_1h"].mean()), 4),
            "top_2_jaccard_overlap_4h": round(float(persistence_df["top_n_persistence_4h"].mean()), 4),
            "top_2_jaccard_overlap_12h": round(float(persistence_df["top_n_persistence_12h"].mean()), 4),
            "top_2_jaccard_overlap_24h": round(float(persistence_df["top_n_persistence_24h"].mean()), 4),
            "avg_top_2_stay_duration_hours": round(float(persistence_df["avg_top_n_duration_hours"].mean()), 2),
            "median_top_2_stay_duration_hours": round(float(persistence_df["median_top_n_duration_hours"].mean()), 2),
            "mean_top_2_transitions_per_fold": round(float(persistence_df["top_n_transitions_count"].mean()), 1)
        }

        try:
            git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        except Exception:
            git_sha = "unknown"

        full_artifact = {
            "experiment_id": "EXP-CS-RB-001",
            "experiment_title": "Cross-Sectional Rebalance Frequency and Turnover Attribution",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit_sha": git_sha,
            "universe_symbols": self.symbols,
            "wfo_folds": self.n_splits,
            "embargo_bars": int(self.sample_bars * self.embargo_pct),
            "friction_assumptions": {
                "maker_fee_bps": self.fee_rate * 10000,
                "slippage_bps": self.slippage * 10000,
                "total_round_trip_bps": (self.fee_rate + self.slippage) * 20000
            },
            "comparison_summary": comparison_summary,
            "rank_persistence_metrics": avg_persistence
        }

        # Export artifacts
        out_dir = "artifacts/cross_sectional/EXP-CS-RB-001"
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs("results/cross_sectional", exist_ok=True)
        os.makedirs("docs/research", exist_ok=True)

        fold_df.to_csv(os.path.join(out_dir, "fold_results.csv"), index=False)
        persistence_df.to_csv(os.path.join(out_dir, "rank_persistence_folds.csv"), index=False)
        summary_df.to_csv(os.path.join(out_dir, "rebalance_comparison_summary.csv"), index=False)

        with open(os.path.join(out_dir, "summary.json"), "w") as f:
            json.dump(full_artifact, f, indent=2)

        with open("results/cross_sectional/rebalance_frequency_analysis.json", "w") as f:
            json.dump(full_artifact, f, indent=2)

        return full_artifact


if __name__ == "__main__":
    runner = RebalanceFrequencyRunner()
    res = runner.run_frequency_sweep()
    print("\nRebalance Frequency Sweep Completed Successfully:")
    print(json.dumps(res, indent=2))
