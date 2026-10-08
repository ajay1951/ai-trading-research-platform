"""
P1-3: Volatility Parity & Risk-Managed Position Sizing Benchmark Engine
======================================================================
Evaluates predefined volatility-aware position sizing on the validated 48H Long-Only Top-2 strategy:
1. Strategy A: Equal Weight Baseline (EXP-CS-P13-EQ: 50% / 50%).
2. Strategy B: Inverse Volatility Weighting (EXP-CS-P13-IV: w_i = (1/vol_i) / sum(1/vol_j)).
3. Strategy C: Volatility-Capped Inverse Volatility (EXP-CS-P13-IV-CAP: min 25%, max 75%).
4. Transaction Cost Sensitivity (0 bps, 12 bps, 20 bps).
5. SOL Dependency Sensitivity (Full Universe vs Without SOLUSDT).
6. Asset Exposure & Risk Contribution Attribution.
"""

import os
import sys
import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

from evaluation.cross_sectional import CrossSectionalRanker, simulate_cross_sectional_portfolio
from evaluation.volatility_sizing import VolatilitySizingEngine
from training.robustness_validation import RobustnessValidationRunner, UNIVERSE_SYMBOLS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("P13Benchmark")

SIZING_MODES = ["equal", "inverse_vol", "iv_capped"]
COST_ASSUMPTIONS_BPS = [0.0, 12.0, 20.0]


class P13BenchmarkRunner:
    def __init__(self, data_dir: str = "data"):
        self.runner = RobustnessValidationRunner(data_dir=data_dir)
        self.symbols = UNIVERSE_SYMBOLS
        self.baseline_fee_rate = 0.0004
        self.baseline_slippage = 0.0002
        self.vol_window = 168 # 7 days (predefined)

    def execute_p13_suite(self) -> Dict[str, Any]:
        logger.info("Loading universe and generating out-of-sample predictions across 5 folds...")
        prices_df, asset_dfs = self.runner.load_and_align_universe()
        fold_data = self.runner.generate_walk_forward_predictions(prices_df, asset_dfs)

        # 1. Compute historical rolling realized volatility across entire price panel point-in-time
        logger.info(f"Computing point-in-time historical volatility (window={self.vol_window} bars)...")
        vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=self.vol_window)

        # ---------------------------------------------------------
        # 1. Primary Strategy Comparison (48H Cadence at 12 bps)
        # ---------------------------------------------------------
        logger.info("Executing Primary 48H Strategy Comparison (EQ vs IV vs IV-CAP)...")
        strategy_fold_results: Dict[str, List[Dict[str, Any]]] = {mode: [] for mode in SIZING_MODES}
        fold_level_comparison_rows = []

        for fd in fold_data:
            fold_id = fd["fold"]
            test_prices = fd["prices_df"]
            vol_fold = vol_panel.reindex(test_prices.index)

            # Raw un-sized weights (50% / 50% Top 2)
            w_raw = RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2)
            
            # Sizing for each mode
            fold_row = {"fold": fold_id, "test_period": fd["test_period"]}

            for mode in SIZING_MODES:
                w_sized = VolatilitySizingEngine.size_portfolio(w_raw, vol_fold, mode=mode)
                w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_sized, interval_bars=48)
                
                m = simulate_cross_sectional_portfolio(
                    test_prices,
                    w_sched,
                    fee_rate=self.baseline_fee_rate,
                    slippage=self.baseline_slippage
                )
                m.update({"fold": fold_id, "mode": mode})
                strategy_fold_results[mode].append(m)

                prefix = "eq" if mode == "equal" else ("iv" if mode == "inverse_vol" else "iv_cap")
                fold_row[f"{prefix}_net_return_pct"] = m["return_pct"]
                fold_row[f"{prefix}_gross_return_pct"] = m["gross_return_pct"]
                fold_row[f"{prefix}_costs_pct"] = m["total_costs_pct"]
                fold_row[f"{prefix}_sharpe"] = m["sharpe"]
                fold_row[f"{prefix}_sortino"] = m["sortino"]
                fold_row[f"{prefix}_max_dd_pct"] = m["max_drawdown"]
                fold_row[f"{prefix}_turnover"] = m["turnover"]
                fold_row[f"{prefix}_trades"] = m["trades"]

            fold_level_comparison_rows.append(fold_row)

        fold_comp_df = pd.DataFrame(fold_level_comparison_rows)

        # Aggregate metrics for each strategy
        aggregate_summary = []
        for mode in SIZING_MODES:
            folds = strategy_fold_results[mode]
            ret_arr = [f["return_pct"] for f in folds]
            gross_arr = [f["gross_return_pct"] for f in folds]
            costs_arr = [f["total_costs_pct"] for f in folds]
            sharpe_arr = [f["sharpe"] for f in folds]
            sortino_arr = [f["sortino"] for f in folds]
            dd_arr = [f["max_drawdown"] for f in folds]
            turnover_arr = [f["turnover"] for f in folds]
            trades_arr = [f["trades"] for f in folds]
            hold_arr = [f["avg_holding_period_hours"] for f in folds]

            # Compute Calmar ratio: Annualized Return / Max DD
            mean_ret = float(np.mean(ret_arr))
            mean_dd = float(np.mean(dd_arr))
            # 5 folds of ~1 month each = ~5 months out-of-sample (~0.417 year)
            ann_ret = (mean_ret * (8760.0 / (692.0))) if 692 > 0 else mean_ret
            calmar = round(ann_ret / max(mean_dd, 1e-4), 2)

            name = "Equal Weight (EXP-CS-P13-EQ)" if mode == "equal" else (
                "Inverse Volatility (EXP-CS-P13-IV)" if mode == "inverse_vol" else
                "IV Capped [25%, 75%] (EXP-CS-P13-IV-CAP)"
            )

            aggregate_summary.append({
                "strategy": name,
                "mode": mode,
                "mean_net_return_pct": round(mean_ret, 2),
                "median_net_return_pct": round(float(np.median(ret_arr)), 2),
                "mean_gross_return_pct": round(float(np.mean(gross_arr)), 2),
                "mean_costs_pct": round(float(np.mean(costs_arr)), 2),
                "mean_sharpe": round(float(np.mean(sharpe_arr)), 2),
                "mean_sortino": round(float(np.mean(sortino_arr)), 2),
                "mean_max_dd_pct": round(mean_dd, 2),
                "calmar_ratio": calmar,
                "mean_daily_turnover": round(float(np.mean(turnover_arr)), 4),
                "mean_trades": round(float(np.mean(trades_arr)), 1),
                "mean_holding_period_hours": round(float(np.mean(hold_arr)), 2),
                "profitable_folds": f"{int((np.array(ret_arr) > 0).sum())}/5",
                "worst_fold_return_pct": round(float(np.min(ret_arr)), 2),
                "best_fold_return_pct": round(float(np.max(ret_arr)), 2),
                "fold_std_dev_pct": round(float(np.std(ret_arr)), 2)
            })

        summary_df = pd.DataFrame(aggregate_summary)

        # ---------------------------------------------------------
        # 2. Asset Exposure & Weight Distribution Analysis
        # ---------------------------------------------------------
        logger.info("Executing Asset Exposure & Weight Distribution Analysis...")
        asset_exposure_rows = []

        fold_slices_eq = []
        fold_slices_iv = []
        fold_slices_iv_cap = []

        for fd in fold_data:
            test_prices = fd["prices_df"]
            vol_fold = vol_panel.reindex(test_prices.index)
            w_raw = RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2)
            w_eq = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)
            w_iv = CrossSectionalRanker.apply_rebalance_frequency(
                VolatilitySizingEngine.size_portfolio(w_raw, vol_fold, mode="inverse_vol"), interval_bars=48
            )
            w_iv_cap = CrossSectionalRanker.apply_rebalance_frequency(
                VolatilitySizingEngine.size_portfolio(w_raw, vol_fold, mode="iv_capped"), interval_bars=48
            )
            rebal_mask = [i % 48 == 0 for i in range(len(w_raw))]
            fold_slices_eq.append(w_eq.iloc[rebal_mask])
            fold_slices_iv.append(w_iv.iloc[rebal_mask])
            fold_slices_iv_cap.append(w_iv_cap.iloc[rebal_mask])

        for sym in self.symbols:
            eq_weights = []
            iv_weights = []
            iv_cap_weights = []
            selection_counts = 0
            total_rebal_points = 0

            for r_eq, r_iv, r_iv_cap in zip(fold_slices_eq, fold_slices_iv, fold_slices_iv_cap):
                if sym in r_eq.columns:
                    eq_weights.extend(r_eq[sym].tolist())
                    iv_weights.extend(r_iv[sym].tolist())
                    iv_cap_weights.extend(r_iv_cap[sym].tolist())
                    selection_counts += int((r_eq[sym] > 0).sum())
                    total_rebal_points += len(r_eq)

            sel_pct = (selection_counts / max(1, total_rebal_points)) * 100.0
            
            # Active non-zero weights
            active_eq = [w for w in eq_weights if w > 0]
            active_iv = [w for w in iv_weights if w > 0]
            active_iv_cap = [w for w in iv_cap_weights if w > 0]

            asset_exposure_rows.append({
                "symbol": sym,
                "selection_pct": round(sel_pct, 2),
                "eq_avg_weight_pct": round(float(np.mean(active_eq) * 100.0), 2) if active_eq else 0.0,
                "iv_avg_weight_pct": round(float(np.mean(active_iv) * 100.0), 2) if active_iv else 0.0,
                "iv_cap_avg_weight_pct": round(float(np.mean(active_iv_cap) * 100.0), 2) if active_iv_cap else 0.0,
                "iv_raw_max_weight_pct": round(float(np.max(active_iv) * 100.0), 2) if active_iv else 0.0,
                "iv_raw_min_weight_pct": round(float(np.min(active_iv) * 100.0), 2) if active_iv else 0.0,
                "iv_cap_max_weight_pct": round(float(np.max(active_iv_cap) * 100.0), 2) if active_iv_cap else 0.0,
                "iv_cap_min_weight_pct": round(float(np.min(active_iv_cap) * 100.0), 2) if active_iv_cap else 0.0
            })

        asset_exposure_df = pd.DataFrame(asset_exposure_rows).sort_values("selection_pct", ascending=False)

        # ---------------------------------------------------------
        # 3. Cap Activation Diagnostics (EXP-CS-P13-IV-CAP)
        # ---------------------------------------------------------
        logger.info("Executing Cap Activation Diagnostics across all rebalance points...")
        all_rebal_decisions = []
        total_rebal_events = 0
        total_cap_activations = 0
        total_upper_hits = 0
        total_lower_hits = 0
        global_max_raw = 0.0
        global_min_raw = 100.0
        global_max_final = 0.0
        global_min_final = 100.0

        for fd in fold_data:
            w_raw = RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2)
            rebal_indices = [i for i in range(len(w_raw)) if i % 48 == 0]
            rebal_df = w_raw.iloc[rebal_indices]
            vol_rebal = vol_panel.reindex(rebal_df.index)

            diag = VolatilitySizingEngine.compute_cap_diagnostics(rebal_df, vol_rebal)
            total_rebal_events += diag["total_rebalance_events"]
            total_cap_activations += diag["cap_activation_count"]
            total_upper_hits += diag["upper_cap_hits"]
            total_lower_hits += diag["lower_cap_hits"]
            global_max_raw = max(global_max_raw, diag["max_raw_weight_pct"])
            global_min_raw = min(global_min_raw, diag["min_raw_weight_pct"])
            global_max_final = max(global_max_final, diag["max_final_weight_pct"])
            global_min_final = min(global_min_final, diag["min_final_weight_pct"])
            all_rebal_decisions.extend(diag["all_decisions"])

        overall_cap_activation_rate = round((total_cap_activations / max(1, total_rebal_events)) * 100.0, 2)
        cap_summary_report = {
            "total_rebalance_events": total_rebal_events,
            "cap_activation_count": total_cap_activations,
            "cap_activation_rate_pct": overall_cap_activation_rate,
            "upper_cap_hits": total_upper_hits,
            "lower_cap_hits": total_lower_hits,
            "max_raw_weight_pct": round(global_max_raw, 2),
            "min_raw_weight_pct": round(global_min_raw, 2),
            "max_final_weight_pct": round(global_max_final, 2),
            "min_final_weight_pct": round(global_min_final, 2),
            "cap_lower_bound_pct": 25.0,
            "cap_upper_bound_pct": 75.0,
            "is_cap_binding": (total_cap_activations > 0),
            "sample_decisions": all_rebal_decisions[:10]
        }

        # ---------------------------------------------------------
        # 3. Component Volatility Risk Contribution Analysis
        # ---------------------------------------------------------
        logger.info("Executing Portfolio Risk Contribution Analysis...")
        # Concatenate returns across all test periods to evaluate risk contributions
        all_test_prices = pd.concat([fd["prices_df"] for fd in fold_data]).sort_index()
        all_test_ret = ((all_test_prices - all_test_prices.shift(1)) / all_test_prices.shift(1)).fillna(0.0)

        all_w_eq = pd.concat([
            CrossSectionalRanker.apply_rebalance_frequency(
                RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2), interval_bars=48
            ) for fd in fold_data
        ]).sort_index()

        all_w_iv = pd.concat([
            CrossSectionalRanker.apply_rebalance_frequency(
                VolatilitySizingEngine.size_portfolio(
                    RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2),
                    vol_panel.reindex(fd["prices_df"].index),
                    mode="inverse_vol"
                ), interval_bars=48
            ) for fd in fold_data
        ]).sort_index()

        all_w_iv_cap = pd.concat([
            CrossSectionalRanker.apply_rebalance_frequency(
                VolatilitySizingEngine.size_portfolio(
                    RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2),
                    vol_panel.reindex(fd["prices_df"].index),
                    mode="iv_capped"
                ), interval_bars=48
            ) for fd in fold_data
        ]).sort_index()

        risk_contrib_eq = VolatilitySizingEngine.compute_risk_contributions(all_test_ret, all_w_eq)
        risk_contrib_iv = VolatilitySizingEngine.compute_risk_contributions(all_test_ret, all_w_iv)
        risk_contrib_iv_cap = VolatilitySizingEngine.compute_risk_contributions(all_test_ret, all_w_iv_cap)

        # ---------------------------------------------------------
        # 4. SOL Dependency Sensitivity (Full vs Without SOL)
        # ---------------------------------------------------------
        logger.info("Executing SOL Dependency Sensitivity for P1-3 Strategies...")
        symbols_no_sol = [s for s in self.symbols if s != "SOLUSDT"]
        sol_sensitivity_records = []

        for mode in SIZING_MODES:
            full_folds = []
            nosol_folds = []

            for fd in fold_data:
                test_prices = fd["prices_df"]
                vol_fold = vol_panel.reindex(test_prices.index)

                # Full
                w_full_raw = RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2)
                w_full_sized = VolatilitySizingEngine.size_portfolio(w_full_raw, vol_fold, mode=mode)
                w_full_sched = CrossSectionalRanker.apply_rebalance_frequency(w_full_sized, interval_bars=48)
                m_full = simulate_cross_sectional_portfolio(test_prices, w_full_sched, fee_rate=self.baseline_fee_rate, slippage=self.baseline_slippage)
                full_folds.append(m_full)

                # No SOL
                w_nosol_raw = RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2, symbols_subset=symbols_no_sol)
                w_nosol_sized = VolatilitySizingEngine.size_portfolio(w_nosol_raw, vol_fold, mode=mode)
                w_nosol_sched = CrossSectionalRanker.apply_rebalance_frequency(w_nosol_sized, interval_bars=48)
                m_nosol = simulate_cross_sectional_portfolio(test_prices, w_nosol_sched, fee_rate=self.baseline_fee_rate, slippage=self.baseline_slippage)
                nosol_folds.append(m_nosol)

            ret_full = [f["return_pct"] for f in full_folds]
            ret_nosol = [f["return_pct"] for f in nosol_folds]

            sol_sensitivity_records.append({
                "mode": mode,
                "strategy": "Equal Weight" if mode == "equal" else ("Inverse Vol" if mode == "inverse_vol" else "IV Capped"),
                "full_mean_return_pct": round(float(np.mean(ret_full)), 2),
                "full_mean_sharpe": round(float(np.mean([f["sharpe"] for f in full_folds])), 2),
                "full_max_dd_pct": round(float(np.mean([f["max_drawdown"] for f in full_folds])), 2),
                "nosol_mean_return_pct": round(float(np.mean(ret_nosol)), 2),
                "nosol_mean_sharpe": round(float(np.mean([f["sharpe"] for f in nosol_folds])), 2),
                "nosol_max_dd_pct": round(float(np.mean([f["max_drawdown"] for f in nosol_folds])), 2),
                "sol_delta_return_pct": round(float(np.mean(ret_full) - np.mean(ret_nosol)), 2)
            })

        # ---------------------------------------------------------
        # 5. Transaction Cost Sensitivity (0, 12, 20 bps)
        # ---------------------------------------------------------
        logger.info("Executing Transaction Cost Sensitivity for P1-3 Strategies...")
        cost_sensitivity_records = []

        for cost_bps in COST_ASSUMPTIONS_BPS:
            fee_rate = (cost_bps / 20000.0) * (2.0 / 3.0)
            slippage = (cost_bps / 20000.0) * (1.0 / 3.0)

            for mode in SIZING_MODES:
                folds = []
                for fd in fold_data:
                    test_prices = fd["prices_df"]
                    vol_fold = vol_panel.reindex(test_prices.index)
                    w_raw = RobustnessValidationRunner._compute_weights_series(fd["preds_df"], top_n=2)
                    w_sized = VolatilitySizingEngine.size_portfolio(w_raw, vol_fold, mode=mode)
                    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_sized, interval_bars=48)
                    m = simulate_cross_sectional_portfolio(test_prices, w_sched, fee_rate=fee_rate, slippage=slippage)
                    folds.append(m)

                ret_arr = [f["return_pct"] for f in folds]
                gross_arr = [f["gross_return_pct"] for f in folds]
                costs_arr = [f["total_costs_pct"] for f in folds]
                sharpe_arr = [f["sharpe"] for f in folds]
                dd_arr = [f["max_drawdown"] for f in folds]
                turnover_arr = [f["turnover"] for f in folds]

                cost_sensitivity_records.append({
                    "cost_bps": cost_bps,
                    "mode": mode,
                    "strategy": "Equal Weight" if mode == "equal" else ("Inverse Vol" if mode == "inverse_vol" else "IV Capped"),
                    "mean_net_return_pct": round(float(np.mean(ret_arr)), 2),
                    "mean_gross_return_pct": round(float(np.mean(gross_arr)), 2),
                    "mean_costs_pct": round(float(np.mean(costs_arr)), 2),
                    "mean_sharpe": round(float(np.mean(sharpe_arr)), 2),
                    "mean_max_dd_pct": round(float(np.mean(dd_arr)), 2),
                    "mean_daily_turnover": round(float(np.mean(turnover_arr)), 4),
                    "profitable_folds": f"{int((np.array(ret_arr) > 0).sum())}/5"
                })

        # ---------------------------------------------------------
        # Export Artifacts
        # ---------------------------------------------------------
        try:
            git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        except Exception:
            git_sha = "unknown"

        full_output = {
            "title": "P1-3: Volatility Parity & Risk-Managed Position Sizing Benchmark",
            "git_commit_sha": git_sha,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "volatility_parameters": {
                "estimator": "rolling_realized_volatility",
                "window_hours": self.vol_window,
                "annualization_factor": "sqrt(24 * 365)"
            },
            "aggregate_summary": aggregate_summary,
            "fold_level_comparison": fold_level_comparison_rows,
            "asset_exposure_analysis": asset_exposure_rows,
            "risk_contributions": {
                "equal_weight": risk_contrib_eq,
                "inverse_vol": risk_contrib_iv,
                "iv_capped": risk_contrib_iv_cap
            },
            "cap_diagnostics": cap_summary_report,
            "sol_dependency": sol_sensitivity_records,
            "cost_sensitivity": cost_sensitivity_records
        }

        dirs = [
            "artifacts/cross_sectional/EXP-CS-P13-EQ",
            "artifacts/cross_sectional/EXP-CS-P13-IV",
            "artifacts/cross_sectional/EXP-CS-P13-IV-CAP",
            "artifacts/cross_sectional/EXP-CS-P13-COST",
            "artifacts/cross_sectional/EXP-CS-P13-SOL",
            "results/cross_sectional"
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        summary_df.to_csv("artifacts/cross_sectional/EXP-CS-P13-EQ/summary.csv", index=False)
        fold_comp_df.to_csv("artifacts/cross_sectional/EXP-CS-P13-EQ/fold_comparison.csv", index=False)
        asset_exposure_df.to_csv("artifacts/cross_sectional/EXP-CS-P13-IV/asset_exposure.csv", index=False)
        pd.DataFrame(cost_sensitivity_records).to_csv("artifacts/cross_sectional/EXP-CS-P13-COST/cost_sensitivity.csv", index=False)
        pd.DataFrame(sol_sensitivity_records).to_csv("artifacts/cross_sectional/EXP-CS-P13-SOL/sol_sensitivity.csv", index=False)

        with open("artifacts/cross_sectional/EXP-CS-P13-IV-CAP/cap_diagnostics.json", "w") as f:
            json.dump(cap_summary_report, f, indent=2)

        with open("results/cross_sectional/p1_3_volatility_sizing.json", "w") as f:
            json.dump(full_output, f, indent=2)

        logger.info("P1-3 Benchmark completed successfully and exported to results/cross_sectional/p1_3_volatility_sizing.json")
        return full_output


if __name__ == "__main__":
    runner = P13BenchmarkRunner()
    res = runner.execute_p13_suite()
    print("\nP1-3 STRATEGY SUMMARY:")
    print(pd.DataFrame(res["aggregate_summary"]).to_string(index=False))
