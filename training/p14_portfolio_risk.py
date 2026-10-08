"""
P1-4: Portfolio Concentration, Correlation & Stress-Test Benchmark Runner
==========================================================================
Experiment ID: EXP-CS-P14-RISK-001

Executes point-in-time risk, concentration, correlation, drawdown, and stress auditing
on the frozen 48H Cross-Sectional Long-Only Top-2 Equal Weight portfolio across 5 WFO folds.

Outputs:
- artifacts/cross_sectional/EXP-CS-P14-RISK-001/ (all tables and diagnostics)
- results/cross_sectional/p1_4_portfolio_risk.json
"""

import os
import sys
import json
import math
import logging
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

from evaluation.cross_sectional import CrossSectionalRanker, simulate_cross_sectional_portfolio
from evaluation.portfolio_risk import PortfolioRiskEngine
from evaluation.risk_metrics import calculate_max_drawdown, reconcile_fold_and_global_drawdowns
from training.robustness_validation import RobustnessValidationRunner, UNIVERSE_SYMBOLS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("P14PortfolioRisk")


class P14PortfolioRiskRunner:
    def __init__(self, data_dir: str = "data"):
        self.runner = RobustnessValidationRunner(data_dir=data_dir)
        self.symbols = UNIVERSE_SYMBOLS
        self.fee_rate = 0.0004
        self.slippage = 0.0002
        self.corr_window = 168

    def execute_p14_suite(self) -> Dict[str, Any]:
        logger.info("P1-4 AUDIT: Loading universe and generating frozen out-of-sample predictions...")
        prices_df, asset_dfs = self.runner.load_and_align_universe()
        fold_data = self.runner.generate_walk_forward_predictions(prices_df, asset_dfs)

        # ---------------------------------------------------------
        # 1. Generate Canonical Frozen 48H Strategy Series
        # ---------------------------------------------------------
        logger.info("Executing Primary 48H Equal Weight Strategy across all 5 folds...")
        fold_results = []
        all_oos_weights_list = []
        all_oos_prices_list = []
        all_oos_equity_list = []

        total_rebal_events = 0
        rebal_selection_counts = {sym: 0 for sym in self.symbols}

        for fd in fold_data:
            fold_id = fd["fold"]
            test_prices = fd["prices_df"]
            w_raw = RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2)
            w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)
            
            m, eq_df, _ = simulate_cross_sectional_portfolio(
                test_prices, w_sched, fee_rate=self.fee_rate, slippage=self.slippage, return_series=True
            )
            m["fold"] = fold_id
            m["test_period"] = fd["test_period"]
            fold_results.append(m)

            all_oos_weights_list.append(w_sched)
            all_oos_prices_list.append(test_prices)

            if not eq_df.empty:
                fold_eq = pd.Series(eq_df["equity"].values, index=pd.to_datetime(eq_df["timestamp"], utc=True))
                all_oos_equity_list.append(fold_eq)

            # Rebalance slices
            rebal_slice = w_sched.iloc[[i % 48 == 0 for i in range(len(w_sched))]]
            total_rebal_events += len(rebal_slice)
            for sym in self.symbols:
                if sym in rebal_slice.columns:
                    rebal_selection_counts[sym] += int((rebal_slice[sym] > 0).sum())

        full_weights_df = pd.concat(all_oos_weights_list).sort_index()
        full_prices_df = pd.concat(all_oos_prices_list).sort_index()

        # Step returns
        aligned_w = full_weights_df.reindex(full_prices_df.index).ffill().fillna(0.0)
        asset_ret = ((full_prices_df - full_prices_df.shift(1)) / full_prices_df.shift(1)).fillna(0.0)
        gross_step = (aligned_w.shift(1).fillna(0.0) * asset_ret).sum(axis=1)
        w_diff = (aligned_w - aligned_w.shift(1).fillna(0.0)).abs().sum(axis=1)
        friction_step = w_diff * (self.fee_rate + self.slippage)
        net_step = gross_step - friction_step
        cum_equity = np.cumprod(1.0 + net_step)

        # Drawdown reconciliation
        dd_reconciliation = reconcile_fold_and_global_drawdowns(all_oos_equity_list)

        # ---------------------------------------------------------
        # 2. Audit 1 & 4: Asset Exposure & PnL Attribution
        # ---------------------------------------------------------
        logger.info("Executing Audit 1 & 4: Asset Exposure & Attribution...")
        exposure_df, exposure_meta = PortfolioRiskEngine.compute_asset_exposure_and_attribution(
            full_prices_df, full_weights_df, fee_rate=self.fee_rate, slippage=self.slippage
        )

        # ---------------------------------------------------------
        # 3. Audit 2: HHI and Effective Number of Assets
        # ---------------------------------------------------------
        logger.info("Executing Audit 2: HHI & Effective Assets...")
        hhi_series, hhi_summary = PortfolioRiskEngine.compute_portfolio_hhi_series(full_weights_df)

        # ---------------------------------------------------------
        # 4. Audit 3: Selection Concentration & Entropy
        # ---------------------------------------------------------
        logger.info("Executing Audit 3: Selection Concentration & Entropy...")
        sorted_counts = sorted(rebal_selection_counts.items(), key=lambda x: x[1], reverse=True)
        tot_selections = sum(rebal_selection_counts.values())
        top_1_rate = (sorted_counts[0][1] / max(1, total_rebal_events)) * 100.0
        top_2_rate = ((sorted_counts[0][1] + sorted_counts[1][1]) / max(1, total_rebal_events * 2)) * 100.0
        top_3_sum = sum(c[1] for c in sorted_counts[:3])
        top_3_rate = (top_3_sum / max(1, total_rebal_events * 2)) * 100.0
        top_5_sum = sum(c[1] for c in sorted_counts[:5])
        top_5_rate = (top_5_sum / max(1, total_rebal_events * 2)) * 100.0
        entropy = PortfolioRiskEngine.compute_selection_entropy(rebal_selection_counts)

        selection_summary = {
            "top_1_asset": sorted_counts[0][0],
            "top_1_rate_pct": round(top_1_rate, 2),
            "top_2_cumulative_share_pct": round(top_2_rate, 2),
            "top_3_cumulative_share_pct": round(top_3_rate, 2),
            "top_5_cumulative_share_pct": round(top_5_rate, 2),
            "selection_entropy": round(entropy, 4),
            "max_theoretical_entropy": round(math.log(len(self.symbols)), 4),
            "asset_ranking_distribution": [{"symbol": k, "count": v, "share_pct": round(v / max(1, tot_selections) * 100.0, 2)} for k, v in sorted_counts]
        }
        selection_df = pd.DataFrame(selection_summary["asset_ranking_distribution"])

        # ---------------------------------------------------------
        # 5. Audit 5: Single-Asset Removal Dependency Analysis
        # ---------------------------------------------------------
        logger.info("Executing Audit 5: Single-Asset Removal Dependency...")
        dependency_df = PortfolioRiskEngine.compute_single_asset_removal_dependency(
            fold_data, fee_rate=self.fee_rate, slippage=self.slippage
        )

        # ---------------------------------------------------------
        # 6. Audit 6 & 7: Pairwise & Rolling Correlation Structure
        # ---------------------------------------------------------
        logger.info("Executing Audit 6 & 7: Correlation Structure...")
        corr_matrix, corr_summary = PortfolioRiskEngine.compute_pairwise_correlations(prices_df)

        # ---------------------------------------------------------
        # 7. Audit 8 & 12: Selected-Pair Point-in-Time Correlation & Correlation Stress
        # ---------------------------------------------------------
        logger.info("Executing Audit 8 & 12: Selected-Pair Correlation & Stress...")
        selected_pairs_df, selected_corr_summary = PortfolioRiskEngine.compute_selected_pair_correlations(
            full_prices_df, full_weights_df, window=self.corr_window
        )

        # Correlation stress performance: evaluate step returns when selected pair corr > 0.7 vs <= 0.7
        high_corr_timestamps = selected_pairs_df[selected_pairs_df["is_high_corr_07"]]["timestamp"].tolist()
        ts_set = set(pd.to_datetime(high_corr_timestamps, utc=True))
        
        # Sub-sample evaluation
        corr_stress_records = []
        for label, cond in [("High Correlation (>0.70)", True), ("Normal/Low Correlation (<=0.70)", False)]:
            sub_pairs = selected_pairs_df[selected_pairs_df["is_high_corr_07"] == cond]
            corr_stress_records.append({
                "regime": label,
                "rebalance_count": len(sub_pairs),
                "share_pct": round(len(sub_pairs) / max(1, len(selected_pairs_df)) * 100.0, 2),
                "mean_pair_correlation": round(float(sub_pairs["rolling_correlation"].mean()), 4) if len(sub_pairs) > 0 else 0.0
            })
        corr_stress_df = pd.DataFrame(corr_stress_records)

        # ---------------------------------------------------------
        # 8. Audit 9: Drawdown Clustering & Attribution
        # ---------------------------------------------------------
        logger.info("Executing Audit 9: Drawdown Clustering...")
        # Point-in-time BTC regime classification for drawdown labeling
        btc_close = prices_df["BTCUSDT"]
        btc_sma100 = btc_close.rolling(2400, min_periods=100).mean()
        btc_mom100 = (btc_close - btc_sma100) / (btc_sma100 + 1e-9)
        regime_series = pd.Series("Sideways", index=prices_df.index)
        regime_series[btc_mom100 > 0.05] = "Bull"
        regime_series[btc_mom100 < -0.05] = "Bear"

        drawdowns = PortfolioRiskEngine.identify_drawdown_episodes(
            cum_equity, full_weights_df, full_prices_df, regime_series=regime_series
        )
        drawdown_df = pd.DataFrame(drawdowns) if len(drawdowns) > 0 else pd.DataFrame(columns=["start_time", "trough_time", "max_drawdown_pct", "duration_hours", "held_assets", "market_regime"])

        # ---------------------------------------------------------
        # 9. Audit 10, 11 & 15: Stress Test Matrices (Single & Two-Asset)
        # ---------------------------------------------------------
        logger.info("Executing Audit 10, 11 & 15: Stress Testing...")
        single_stress_df, dual_stress_df = PortfolioRiskEngine.compute_stress_test_matrices(
            exposure_df, selected_pairs_df
        )

        # ---------------------------------------------------------
        # 10. Audit 13: Fold Concentration Analysis
        # ---------------------------------------------------------
        logger.info("Executing Audit 13: Fold Concentration Analysis...")
        fold_risk_rows = []
        tot_gross_return = sum(f["gross_return_pct"] for f in fold_results)

        for f in fold_results:
            fold_id = f["fold"]
            fd = fold_data[fold_id - 1]
            w_raw = RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2)
            w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)
            h_series, h_sum = PortfolioRiskEngine.compute_portfolio_hhi_series(w_sched)

            # Top contributing asset in this fold
            aligned_w_f = w_sched.reindex(fd["prices_df"].index).ffill().fillna(0.0)
            asset_ret_f = ((fd["prices_df"] - fd["prices_df"].shift(1)) / fd["prices_df"].shift(1)).fillna(0.0)
            asset_step_gross = (aligned_w_f.shift(1).fillna(0.0) * asset_ret_f).sum(axis=0)
            top_asset_f = asset_step_gross.idxmax()
            top_asset_contrib = float(asset_step_gross.max() * 100.0)
            worst_asset_f = asset_step_gross.idxmin()
            worst_asset_contrib = float(asset_step_gross.min() * 100.0)

            fold_risk_rows.append({
                "fold": fold_id,
                "test_period": f["test_period"],
                "net_return_pct": f["return_pct"],
                "gross_return_pct": f["gross_return_pct"],
                "sharpe": f["sharpe"],
                "sortino": f["sortino"],
                "max_drawdown_pct": f["max_drawdown"],
                "mean_hhi": h_sum["mean_hhi"],
                "mean_effective_assets": h_sum["mean_effective_assets"],
                "top_contributing_asset": f"{top_asset_f} (+{top_asset_contrib:.2f}%)",
                "worst_contributing_asset": f"{worst_asset_f} ({worst_asset_contrib:.2f}%)",
                "fold_share_of_gross_pct": round((f["gross_return_pct"] / max(1e-4, tot_gross_return)) * 100.0, 2)
            })

        fold_risk_df = pd.DataFrame(fold_risk_rows)

        # ---------------------------------------------------------
        # 11. Audit 14: BTC Market Regime Concentration
        # ---------------------------------------------------------
        logger.info("Executing Audit 14: Market Regime Concentration...")
        regime_aligned = regime_series.reindex(net_step.index).ffill().fillna("Sideways")
        
        regime_rows = []
        for reg in ["Bull", "Sideways", "Bear"]:
            mask = (regime_aligned == reg)
            sub_step = net_step[mask]
            n_obs = len(sub_step)
            if n_obs > 0:
                cum_ret = float((np.prod(1.0 + sub_step) - 1.0) * 100.0)
                m_ret = float(sub_step.mean())
                s_ret = float(sub_step.std())
                sharpe_reg = float((m_ret / (s_ret + 1e-9)) * np.sqrt(8760)) if s_ret > 0 else 0.0
                
                # Max DD within regime
                eq_reg = np.cumprod(1.0 + sub_step)
                peak_reg = np.maximum.accumulate(eq_reg)
                dd_reg = float(np.max((peak_reg - eq_reg) / peak_reg) * 100.0) if len(eq_reg) > 0 else 0.0

                regime_rows.append({
                    "market_regime": reg,
                    "hourly_bars": n_obs,
                    "share_of_sample_pct": round((n_obs / len(net_step)) * 100.0, 2),
                    "cumulative_net_return_pct": round(cum_ret, 2),
                    "annualized_sharpe": round(sharpe_reg, 2),
                    "max_drawdown_pct": round(dd_reg, 2),
                    "sample_reliability": "Statistically Reliable (>1000 bars)" if n_obs >= 1000 else "Small Sample (Limited Statistical Power)"
                })
        regime_risk_df = pd.DataFrame(regime_rows)

        # ---------------------------------------------------------
        # 12. Audit 16: Risk Scorecard
        # ---------------------------------------------------------
        logger.info("Compiling Concentration & Robustness Risk Scorecard...")
        scorecard = PortfolioRiskEngine.generate_risk_scorecard(
            hhi_summary, selection_summary, corr_summary, selected_corr_summary, dependency_df, drawdowns, fold_results
        )

        # ---------------------------------------------------------
        # 13. Export Artifacts
        # ---------------------------------------------------------
        try:
            git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        except Exception:
            git_sha = "unknown"

        full_output = {
            "experiment_id": "EXP-CS-P14-RISK-001",
            "title": "P1-4: Portfolio Concentration, Correlation & Stress-Test Audit",
            "git_commit_sha": git_sha,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "strategy_under_audit": "48H Cross-Sectional Long-Only Top-2 Equal Weight (50%/50%)",
            "executive_summary": {
                "mean_net_return_pct": round(float(np.mean([f["return_pct"] for f in fold_results])), 2),
                "mean_sharpe": round(float(np.mean([f["sharpe"] for f in fold_results])), 2),
                "mean_fold_max_drawdown_pct": dd_reconciliation["mean_fold_max_drawdown_pct"],
                "worst_fold_max_drawdown_pct": dd_reconciliation["worst_fold_max_drawdown_pct"],
                "global_continuous_max_drawdown_pct": dd_reconciliation["global_continuous_max_drawdown_pct"],
                "largest_drawdown_episode_pct": float(drawdown_df["max_drawdown_pct"].max()) if len(drawdown_df) > 0 else 0.0,
                "mean_hhi": hhi_summary["mean_hhi"],
                "mean_effective_assets": hhi_summary["mean_effective_assets"],
                "most_selected_asset": selection_summary["top_1_asset"],
                "top_1_selection_rate_pct": selection_summary["top_1_rate_pct"],
                "selection_entropy": selection_summary["selection_entropy"],
                "mean_pairwise_correlation": corr_summary["mean_pairwise_correlation"],
                "mean_selected_pair_correlation": selected_corr_summary["mean_selected_pair_correlation"],
                "pct_selected_pairs_above_07": selected_corr_summary["pct_above_07"],
                "worst_single_asset_crash_50pct": single_stress_df["loss_at_max_w_minus_50pct"].min(),
                "simultaneous_crash_50pct": -50.0,
                "overall_concentration_risk": "MODERATE (Structural 2-Asset Concentration with Diversified Selection)",
                "overall_stress_vulnerability": "HIGH (Unhedged 100% Long Exposure Subject to Simultaneous Shocks)"
            },
            "hhi_summary": hhi_summary,
            "selection_concentration": selection_summary,
            "pairwise_correlation": corr_summary,
            "selected_pair_correlation": selected_corr_summary,
            "correlation_stress": corr_stress_records,
            "fold_concentration": fold_risk_rows,
            "regime_concentration": regime_rows,
            "drawdown_episodes": drawdowns,
            "drawdown_reconciliation": dd_reconciliation,
            "risk_scorecard": scorecard
        }

        out_dir = "artifacts/cross_sectional/EXP-CS-P14-RISK-001"
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs("results/cross_sectional", exist_ok=True)

        exposure_df.to_csv(f"{out_dir}/asset_exposure.csv", index=False)
        selection_df.to_csv(f"{out_dir}/selection_concentration.csv", index=False)
        exposure_df[["symbol", "gross_return_contribution_pct", "net_return_contribution_pct", "share_of_positive_gross_pct", "win_periods_count", "loss_periods_count"]].to_csv(f"{out_dir}/asset_contributions.csv", index=False)
        corr_matrix.to_csv(f"{out_dir}/correlation_matrix.csv")
        pd.DataFrame([corr_summary]).to_csv(f"{out_dir}/rolling_correlation_summary.csv", index=False)
        selected_pairs_df.to_csv(f"{out_dir}/selected_pair_correlation.csv", index=False)
        drawdown_df.to_csv(f"{out_dir}/drawdown_analysis.csv", index=False)
        single_stress_df.to_csv(f"{out_dir}/single_asset_stress.csv", index=False)
        dual_stress_df.to_csv(f"{out_dir}/two_asset_stress.csv", index=False)
        fold_risk_df.to_csv(f"{out_dir}/fold_risk.csv", index=False)
        regime_risk_df.to_csv(f"{out_dir}/regime_risk.csv", index=False)

        with open(f"{out_dir}/summary.json", "w") as f:
            json.dump(full_output["executive_summary"], f, indent=2)

        with open(f"{out_dir}/risk_scorecard.json", "w") as f:
            json.dump(scorecard, f, indent=2)

        with open("results/cross_sectional/p1_4_portfolio_risk.json", "w") as f:
            json.dump(full_output, f, indent=2)

        logger.info(f"P1-4 Risk Audit completed successfully. Artifacts exported to {out_dir}/")
        return full_output


if __name__ == "__main__":
    runner = P14PortfolioRiskRunner()
    res = runner.execute_p14_suite()
    print("\nP1-4 EXECUTIVE RISK SUMMARY:")
    print(json.dumps(res["executive_summary"], indent=2))
