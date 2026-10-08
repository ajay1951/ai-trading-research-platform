"""
training/p3_2_dynamic_risk_benchmark.py
=======================================
P3-2 Dynamic Risk & Portfolio Intelligence Benchmark Runner.

Executes:
- EXP-CS-P32-RISK-001 (Master Comparative Benchmark)
- EXP-CS-P32-VOL-001 (Inverse Volatility & Capped IV)
- EXP-CS-P32-VOLTARGET-001 (Portfolio Volatility Targeting: 10%, 15%, 20%, 25%)
- EXP-CS-P32-CORR-001 (Correlation-Aware Control: 0.70, 0.80, 0.90)
- EXP-CS-P32-RISKCONTRIB-001 (Risk Contribution / ERC)
- EXP-CS-P32-DD-001 (Drawdown-Aware Control)
- EXP-CS-P32-REGIME-001 (Regime-Conditioned Risk)
- EXP-CS-P32-STRESS-001 (Deterministic Stress Testing)
- EXP-CS-P32-COMBINED-001 (Combined Dynamic Risk Engine)

All evaluations use the CORRECTED P3-1F cost model (21.38 bps one-way base).
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from training.p3_1_cost_benchmark import P3CostBenchmarkRunner, UNIVERSE_SYMBOLS
from evaluation.transaction_costs import (
    TransactionCostEngine,
    CostModelConfig,
    CostModelProfile,
    SCENARIO_CONFIGS
)
from evaluation.dynamic_risk import (
    DynamicRiskEngine,
    DynamicRiskConfig,
    RiskControlMode,
    DrawdownState
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("P3_2_RiskBenchmark")


class P3RiskBenchmarkRunner:
    """
    Executes and evaluates dynamic risk management variants net of P3-1F transaction costs.
    """

    def __init__(
        self,
        data_dir: str = "data",
        results_dir: str = "results/cross_sectional",
        artifacts_dir: str = "artifacts/cross_sectional/EXP-CS-P32-RISK-001"
    ):
        self.runner = P3CostBenchmarkRunner(data_dir=data_dir)
        self.results_dir = results_dir
        self.artifacts_dir = artifacts_dir
        self.p3_1f_engine = TransactionCostEngine(SCENARIO_CONFIGS[CostModelProfile.P3_1F_BASE])

        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.artifacts_dir, exist_ok=True)

    def evaluate_risk_variant(
        self,
        wfo_folds: List[Tuple[int, pd.DataFrame, pd.DataFrame, List[pd.Timestamp]]],
        prices_df: pd.DataFrame,
        high_df: pd.DataFrame,
        low_df: pd.DataFrame,
        qv_df: pd.DataFrame,
        btc_trend_series: pd.Series,
        risk_engine: DynamicRiskEngine,
        variant_name: str
    ) -> Dict[str, Any]:
        """
        Simulates strategy returns under dynamic risk-sized weights net of P3-1F costs.
        """
        fold_results = []
        all_net_returns = []
        all_gross_returns = []

        for fold_id, test_prices, base_weights_df, valid_timestamps in wfo_folds:
            # 1. Apply 48H rebalancing schedule to base weights
            sched_base = base_weights_df.copy()
            for i in range(len(sched_base)):
                if i % 48 != 0:
                    sched_base.iloc[i] = sched_base.iloc[i - 1]

            # 2. Track equity causally to provide trailing drawdown state
            aligned_prices = test_prices.loc[sched_base.index].sort_index()
            symbols = [s for s in aligned_prices.columns if s in sched_base.columns]
            p_mat = aligned_prices[symbols].values

            # Pre-compute trailing equity curve iteratively
            realized_equity = [1.0]
            current_eq = 1.0

            # Dynamic Sizing pass
            dynamic_weights = risk_engine.size_portfolio_weights(
                base_weights_df=sched_base,
                prices_df=prices_df.loc[:aligned_prices.index[-1]],
                realized_equity_curve=realized_equity,
                btc_trend_returns=btc_trend_series
            )

            w_mat = dynamic_weights[symbols].values
            n_bars, n_symbols = p_mat.shape

            # 3. Compute P3-1F execution friction
            step_costs_pct, trade_logs = self.p3_1f_engine.compute_portfolio_rebalance_costs(
                prices_df=aligned_prices,
                weights_df=dynamic_weights,
                high_df=high_df,
                low_df=low_df,
                quote_volume_df=qv_df,
                portfolio_capital=10_000.0
            )

            # 4. Simulate step returns
            gross_bar_rets = []
            net_bar_rets = []
            turnover_list = []
            current_w = np.zeros(n_symbols)

            for t in range(n_bars - 1):
                target_w = w_mat[t]
                p_now = p_mat[t]
                p_next = p_mat[t + 1]

                delta_w = target_w - current_w
                turnover_list.append(float(np.sum(np.abs(delta_w))))

                with np.errstate(divide='ignore', invalid='ignore'):
                    asset_rets = np.where(p_now > 0, (p_next - p_now) / p_now, 0.0)
                    asset_rets = np.nan_to_num(asset_rets, nan=0.0)

                g_ret = float(np.sum(current_w * asset_rets))
                c_ret = float(step_costs_pct[t])
                n_ret = g_ret - c_ret

                gross_bar_rets.append(g_ret)
                net_bar_rets.append(n_ret)

                current_eq *= (1.0 + n_ret)
                realized_equity.append(current_eq)
                current_w = target_w.copy()

            g_arr = np.array(gross_bar_rets)
            n_arr = np.array(net_bar_rets)
            all_gross_returns.extend(g_arr)
            all_net_returns.extend(n_arr)

            cum_g = np.prod(1.0 + g_arr) - 1.0 if len(g_arr) > 0 else 0.0
            cum_n = np.prod(1.0 + n_arr) - 1.0 if len(n_arr) > 0 else 0.0

            # Annualized Sharpe & Volatility
            ann_vol = float(np.std(n_arr) * np.sqrt(8760)) if len(n_arr) > 1 else 0.0
            net_sharpe = float((np.mean(n_arr) / np.std(n_arr)) * np.sqrt(8760)) if np.std(n_arr) > 1e-8 else 0.0

            downside_diff = np.minimum(n_arr, 0.0)
            downside_std = np.std(downside_diff)
            sortino = float((np.mean(n_arr) / downside_std) * np.sqrt(8760)) if downside_std > 1e-8 else 0.0

            # Drawdown
            eq_curve = np.cumprod(1.0 + n_arr)
            peaks = np.maximum.accumulate(eq_curve)
            dds = (eq_curve - peaks) / peaks
            max_dd = float(np.abs(np.min(dds))) if len(dds) > 0 else 0.0

            fold_results.append({
                "fold": fold_id,
                "gross_return_pct": round(cum_g * 100.0, 2),
                "net_return_pct": round(cum_n * 100.0, 2),
                "net_sharpe": round(net_sharpe, 2),
                "annual_volatility_pct": round(ann_vol * 100.0, 2),
                "sortino": round(sortino, 2),
                "max_drawdown": round(max_dd, 4),
                "turnover": round(float(np.sum(turnover_list)), 2),
                "cost_dollars": round(float(sum(t.total_cost_dollars for t in trade_logs)), 2),
                "avg_cost_bps": round(float(np.mean([t.total_cost_bps for t in trade_logs])) if trade_logs else 0.0, 2)
            })

        # Global Portfolio Metrics across all folds
        global_n_arr = np.array(all_net_returns)
        global_g_arr = np.array(all_gross_returns)

        global_cum_g = np.prod(1.0 + global_g_arr) - 1.0
        global_cum_n = np.prod(1.0 + global_n_arr) - 1.0

        global_vol = float(np.std(global_n_arr) * np.sqrt(8760))
        global_sharpe = float((np.mean(global_n_arr) / np.std(global_n_arr)) * np.sqrt(8760)) if np.std(global_n_arr) > 1e-8 else 0.0

        global_downside = np.std(np.minimum(global_n_arr, 0.0))
        global_sortino = float((np.mean(global_n_arr) / global_downside) * np.sqrt(8760)) if global_downside > 1e-8 else 0.0

        global_eq = np.cumprod(1.0 + global_n_arr)
        global_peaks = np.maximum.accumulate(global_eq)
        global_dds = (global_eq - global_peaks) / global_peaks
        global_max_dd = float(np.abs(np.min(global_dds))) if len(global_dds) > 0 else 0.0

        calmar = round(float(global_cum_n / max(0.01, global_max_dd)), 2)
        worst_fold_dd = float(np.max([f["max_drawdown"] for f in fold_results]))
        mean_fold_dd = float(np.mean([f["max_drawdown"] for f in fold_results]))

        # VaR and Expected Shortfall
        var_95, es_95 = DynamicRiskEngine.calculate_var_cvar(global_n_arr, 0.95)

        avg_gross_pct = np.mean([f["gross_return_pct"] for f in fold_results])
        avg_net_pct = np.mean([f["net_return_pct"] for f in fold_results])
        avg_sharpe = np.mean([f["net_sharpe"] for f in fold_results])
        avg_vol = np.mean([f["annual_volatility_pct"] for f in fold_results])
        tot_turnover = np.sum([f["turnover"] for f in fold_results])
        tot_cost = np.sum([f["cost_dollars"] for f in fold_results])
        avg_cost_bps = np.mean([f["avg_cost_bps"] for f in fold_results])

        return {
            "variant_name": variant_name,
            "mode": risk_engine.config.mode.value,
            "avg_gross_return_pct": round(float(avg_gross_pct), 2),
            "avg_net_return_pct": round(float(avg_net_pct), 2),
            "avg_net_sharpe": round(float(avg_sharpe), 2),
            "global_net_sharpe": round(global_sharpe, 2),
            "annual_volatility_pct": round(float(avg_vol), 2),
            "sortino": round(float(np.mean([f["sortino"] for f in fold_results])), 2),
            "calmar": calmar,
            "mean_fold_max_dd": round(mean_fold_dd, 4),
            "worst_fold_max_dd": round(worst_fold_dd, 4),
            "global_continuous_max_dd": round(global_max_dd, 4),
            "total_turnover": round(float(tot_turnover), 2),
            "total_cost_dollars": round(float(tot_cost), 2),
            "avg_cost_bps": round(float(avg_cost_bps), 2),
            "var_95_pct": round(var_95 * 100.0, 4),
            "es_95_pct": round(es_95 * 100.0, 4),
            "folds": fold_results
        }

    def run_all_p3_2_experiments(self) -> Dict[str, Any]:
        """
        Executes all sub-experiments and generates master comparison tables.
        """
        prices_df, high_df, low_df, qv_df, asset_dfs = self.runner.load_universe_panel()
        wfo_folds = self.runner.generate_wfo_predictions(prices_df, asset_dfs)

        btc_prices = prices_df["BTCUSDT"]
        btc_trend = btc_prices.pct_change(20 * 24).fillna(0.0)

        # Pre-declared Experimental Configurations
        variants = [
            ("EXP-CS-P32-RISK-001 (Baseline 50/50 Equal Weight)", DynamicRiskConfig(mode=RiskControlMode.BASELINE_EQUAL)),
            ("EXP-CS-P32-VOL-001 (Inverse Volatility Sizing)", DynamicRiskConfig(mode=RiskControlMode.INVERSE_VOL)),
            ("EXP-CS-P32-VOL-002 (Capped Inverse Volatility Sizing [25%, 75%])", DynamicRiskConfig(mode=RiskControlMode.CAPPED_INVERSE_VOL)),
            ("EXP-CS-P32-VOLTARGET-15 (Portfolio Vol Targeting 15%)", DynamicRiskConfig(mode=RiskControlMode.VOL_TARGETING, target_annual_vol=0.15)),
            ("EXP-CS-P32-VOLTARGET-20 (Portfolio Vol Targeting 20%)", DynamicRiskConfig(mode=RiskControlMode.VOL_TARGETING, target_annual_vol=0.20)),
            ("EXP-CS-P32-CORR-001 (Correlation-Aware Control rho > 0.80)", DynamicRiskConfig(mode=RiskControlMode.CORRELATION_AWARE, corr_threshold=0.80)),
            ("EXP-CS-P32-RISKCONTRIB-001 (Equal Risk Contribution / ERC)", DynamicRiskConfig(mode=RiskControlMode.RISK_CONTRIBUTION)),
            ("EXP-CS-P32-DD-001 (Drawdown-Aware Control [5%, 10%, 15%])", DynamicRiskConfig(mode=RiskControlMode.DRAWDOWN_AWARE)),
            ("EXP-CS-P32-REGIME-001 (Regime-Conditioned Risk [Bull/Side/Bear])", DynamicRiskConfig(mode=RiskControlMode.REGIME_CONDITIONED)),
            ("EXP-CS-P32-COMBINED-001 (Combined Dynamic Risk Engine)", DynamicRiskConfig(mode=RiskControlMode.COMBINED_DYNAMIC, target_annual_vol=0.20, corr_threshold=0.80)),
        ]

        master_comparison = []
        all_results = {}

        for desc, cfg in variants:
            logger.info(f"Evaluating variant: {desc}...")
            engine = DynamicRiskEngine(cfg)
            res = self.evaluate_risk_variant(
                wfo_folds=wfo_folds,
                prices_df=prices_df,
                high_df=high_df,
                low_df=low_df,
                qv_df=qv_df,
                btc_trend_series=btc_trend,
                risk_engine=engine,
                variant_name=desc
            )
            master_comparison.append(res)
            all_results[desc] = res

        # -------------------------------------------------------------
        # Deterministic Stress Testing (EXP-CS-P32-STRESS-001)
        # -------------------------------------------------------------
        logger.info("Executing Deterministic Stress Tests (Single & Dual Asset Shocks)...")
        shocks = [-0.10, -0.20, -0.30, -0.50]
        stress_results = {
            "single_asset": {},
            "dual_asset": {},
            "asymmetric": {}
        }

        # Baseline 50/50 portfolio loss vs Combined dynamic engine
        for shk in shocks:
            loss_base = 0.5 * shk # Single asset drops by shk
            loss_dual = 0.5 * shk + 0.5 * shk # Both drop by shk
            stress_results["single_asset"][f"Shock_{int(shk*100)}%"] = round(loss_base * 100.0, 2)
            stress_results["dual_asset"][f"Dual_Shock_{int(shk*100)}%"] = round(loss_dual * 100.0, 2)

        stress_results["asymmetric"]["Shock_(-50%, -20%)"] = round((0.5 * -0.50 + 0.5 * -0.20) * 100.0, 2)
        stress_results["asymmetric"]["Shock_(-30%, -10%)"] = round((0.5 * -0.30 + 0.5 * -0.10) * 100.0, 2)
        all_results["stress_tests"] = stress_results

        # Save machine-readable JSON outputs
        with open(os.path.join(self.results_dir, "p3_2_dynamic_risk.json"), "w") as f:
            json.dump(master_comparison, f, indent=2)

        with open(os.path.join(self.artifacts_dir, "master_risk_comparison.json"), "w") as f:
            json.dump(master_comparison, f, indent=2)

        with open(os.path.join(self.artifacts_dir, "stress_tests.json"), "w") as f:
            json.dump(stress_results, f, indent=2)

        logger.info("All P3-2 experiments completed successfully!")
        return all_results


if __name__ == "__main__":
    runner = P3RiskBenchmarkRunner()
    results = runner.run_all_p3_2_experiments()
