"""
evaluation/extended_shadow.py
=============================
P4-1 Extended Longitudinal Shadow Study & Non-Interfering Comparison Engine.

Provides:
1. Longitudinal Side-by-Side Inference (Champion vs Challenger).
2. Strict Shadow Isolation (Zero order execution, zero portfolio state mutation).
3. Longitudinal Agreement, Prediction Divergence, Top-2 Selection Jaccard & Portfolio Tracking.
4. Independent Point-in-Time Economic Shadow Accounting under P3-1F transaction costs.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class ExtendedShadowObservation:
    """Detailed observation recorded at each rebalance timestamp."""
    timestamp: str
    rebalance_idx: int
    champion_top2: List[str]
    challenger_top2: List[str]
    selection_agreement: bool
    top2_jaccard: float
    champion_predictions: Dict[str, float]
    challenger_predictions: Dict[str, float]
    directional_agreements: Dict[str, bool]
    mean_abs_prob_diff: float
    champion_ret_step: float
    challenger_ret_step: float
    champion_turnover: float
    challenger_turnover: float
    champion_cost: float
    challenger_cost: float


@dataclass
class ExtendedShadowStudyResult:
    """Comprehensive aggregation of longitudinal shadow study."""
    champion_model_id: str
    challenger_model_id: str
    start_timestamp: str
    end_timestamp: str
    total_bars: int
    total_rebalances: int
    total_predictions_evaluated: int
    mean_directional_agreement: float
    mean_selection_jaccard: float
    prediction_correlation: float
    probability_correlation: float
    champion_gross_return_pct: float
    challenger_gross_return_pct: float
    champion_net_return_pct: float
    challenger_net_return_pct: float
    champion_net_sharpe: float
    challenger_net_sharpe: float
    champion_max_drawdown_pct: float
    challenger_max_drawdown_pct: float
    champion_total_turnover: float
    challenger_total_turnover: float
    champion_total_cost_pct: float
    challenger_total_cost_pct: float
    champion_p50_latency_ms: float
    challenger_p50_latency_ms: float
    champion_p95_latency_ms: float
    challenger_p95_latency_ms: float
    error_count: int
    is_shadow_isolated: bool
    observations: List[ExtendedShadowObservation] = field(default_factory=list)


class ExtendedShadowEngine:
    """
    Executes longitudinal shadow simulations comparing Champion and Challenger models.
    """

    @staticmethod
    def run_longitudinal_study(
        champion_model: Any,
        challenger_model: Any,
        champion_model_id: str,
        challenger_model_id: str,
        prices_df: pd.DataFrame,
        asset_dfs: Dict[str, pd.DataFrame],
        eval_timestamps: List[Any],
        rebalance_interval_bars: int = 48,
        cost_bps_one_way: float = 21.38
    ) -> ExtendedShadowStudyResult:
        """
        Executes extended longitudinal shadow study over eval_timestamps.
        """
        symbols = sorted(list(prices_df.columns))
        feature_cols = [
            c for c in next(iter(asset_dfs.values())).columns
            if c not in ['open', 'high', 'low', 'close', 'quote_volume', 'target', 'timestamp']
        ]

        observations: List[ExtendedShadowObservation] = []
        champ_latencies: List[float] = []
        chall_latencies: List[float] = []
        errors = 0

        # Independent Portfolio Tracking
        champ_weights: Dict[str, float] = {s: 0.0 for s in symbols}
        chall_weights: Dict[str, float] = {s: 0.0 for s in symbols}

        champ_equity = 1.0
        chall_equity = 1.0

        champ_equity_curve = [1.0]
        chall_equity_curve = [1.0]

        all_champ_probs: List[float] = []
        all_chall_probs: List[float] = []

        # Run rebalance cycle simulation
        n_timestamps = len(eval_timestamps)
        rebal_count = 0

        for i in range(0, n_timestamps - rebalance_interval_bars, rebalance_interval_bars):
            decision_ts = eval_timestamps[i]
            exec_ts = eval_timestamps[i + 1]
            rebal_count += 1

            champ_scores: Dict[str, float] = {}
            chall_scores: Dict[str, float] = {}
            dir_agrees: Dict[str, bool] = {}
            prob_diffs: List[float] = []

            for sym in symbols:
                if sym not in asset_dfs or decision_ts not in asset_dfs[sym].index:
                    continue

                row = asset_dfs[sym].loc[decision_ts]
                f_vec = row[feature_cols].values.reshape(1, -1)

                # Champion Inference
                t0 = time.perf_counter()
                try:
                    p_champ = float(champion_model.predict_proba(f_vec)[0, 1])
                except Exception:
                    p_champ = 0.50
                    errors += 1
                champ_lat = (time.perf_counter() - t0) * 1000.0
                champ_latencies.append(champ_lat)

                # Challenger Inference
                t1 = time.perf_counter()
                try:
                    p_chall = float(challenger_model.predict_proba(f_vec)[0, 1])
                except Exception:
                    p_chall = 0.50
                    errors += 1
                chall_lat = (time.perf_counter() - t1) * 1000.0
                chall_latencies.append(chall_lat)

                champ_scores[sym] = p_champ
                chall_scores[sym] = p_chall
                dir_agrees[sym] = (p_champ >= 0.50) == (p_chall >= 0.50)
                prob_diffs.append(abs(p_champ - p_chall))
                all_champ_probs.append(p_champ)
                all_chall_probs.append(p_chall)

            # Top-2 Selection (Equal Weight 50/50)
            sorted_champ = sorted(champ_scores.items(), key=lambda x: x[1], reverse=True)
            sorted_chall = sorted(chall_scores.items(), key=lambda x: x[1], reverse=True)

            champ_top2 = [s[0] for s in sorted_champ[:2]]
            chall_top2 = [s[0] for s in sorted_chall[:2]]

            # Jaccard similarity of selections
            intersection = len(set(champ_top2).intersection(set(chall_top2)))
            union = len(set(champ_top2).union(set(chall_top2)))
            jaccard = intersection / union if union > 0 else 1.0

            # Target weights
            new_champ_w = {s: (0.50 if s in champ_top2 else 0.0) for s in symbols}
            new_chall_w = {s: (0.50 if s in chall_top2 else 0.0) for s in symbols}

            # Turnover
            champ_turnover = sum(abs(new_champ_w[s] - champ_weights[s]) for s in symbols)
            chall_turnover = sum(abs(new_chall_w[s] - chall_weights[s]) for s in symbols)

            champ_cost = champ_turnover * (cost_bps_one_way / 10000.0)
            chall_cost = chall_turnover * (cost_bps_one_way / 10000.0)

            # Asset forward returns over the 48h rebalance period (exec_ts to next_exec_ts)
            next_exec_idx = min(n_timestamps - 1, i + rebalance_interval_bars + 1)
            next_exec_ts = eval_timestamps[next_exec_idx]

            champ_period_ret = 0.0
            chall_period_ret = 0.0

            for sym in symbols:
                p_start = prices_df[sym].loc[exec_ts]
                p_end = prices_df[sym].loc[next_exec_ts]
                r_asset = (p_end - p_start) / p_start

                champ_period_ret += new_champ_w[sym] * r_asset
                chall_period_ret += new_chall_w[sym] * r_asset

            champ_net_step = champ_period_ret - champ_cost
            chall_net_step = chall_period_ret - chall_cost

            champ_equity *= (1.0 + champ_net_step)
            chall_equity *= (1.0 + chall_net_step)

            champ_equity_curve.append(champ_equity)
            chall_equity_curve.append(chall_equity)

            champ_weights = new_champ_w
            chall_weights = new_chall_w

            observations.append(ExtendedShadowObservation(
                timestamp=str(decision_ts),
                rebalance_idx=rebal_count,
                champion_top2=champ_top2,
                challenger_top2=chall_top2,
                selection_agreement=(set(champ_top2) == set(chall_top2)),
                top2_jaccard=round(jaccard, 4),
                champion_predictions=champ_scores,
                challenger_predictions=chall_scores,
                directional_agreements=dir_agrees,
                mean_abs_prob_diff=round(float(np.mean(prob_diffs)), 4),
                champion_ret_step=round(champ_net_step, 4),
                challenger_ret_step=round(chall_net_step, 4),
                champion_turnover=round(champ_turnover, 4),
                challenger_turnover=round(chall_turnover, 4),
                champion_cost=round(champ_cost, 6),
                challenger_cost=round(chall_cost, 6)
            ))

        # Performance Summary
        n_rebal = len(observations)
        champ_rets = [obs.champion_ret_step for obs in observations]
        chall_rets = [obs.challenger_ret_step for obs in observations]

        champ_mean_r, champ_std_r = float(np.mean(champ_rets)), float(np.std(champ_rets))
        chall_mean_r, chall_std_r = float(np.mean(chall_rets)), float(np.std(chall_rets))

        # Annualization factor for 48h rebalance (365 * 24 / 48 = 182.5 cycles/yr)
        ann_factor = np.sqrt(182.5)
        champ_sharpe = (champ_mean_r / champ_std_r * ann_factor) if champ_std_r > 1e-6 else 0.0
        chall_sharpe = (chall_mean_r / chall_std_r * ann_factor) if chall_std_r > 1e-6 else 0.0

        # Drawdowns
        def compute_max_dd(eq_curve: List[float]) -> float:
            arr = np.array(eq_curve)
            peaks = np.maximum.accumulate(arr)
            dds = (peaks - arr) / peaks
            return float(np.max(dds))

        champ_max_dd = compute_max_dd(champ_equity_curve) * 100.0
        chall_max_dd = compute_max_dd(chall_equity_curve) * 100.0

        # Correlations
        std_c, std_ch = float(np.std(all_champ_probs)), float(np.std(all_chall_probs))
        prob_corr = float(np.corrcoef(all_champ_probs, all_chall_probs)[0, 1]) if std_c > 1e-6 and std_ch > 1e-6 else 1.0

        mean_jaccard = float(np.mean([obs.top2_jaccard for obs in observations]))
        dir_agr_rate = float(np.mean([np.mean(list(obs.directional_agreements.values())) for obs in observations]))

        return ExtendedShadowStudyResult(
            champion_model_id=champion_model_id,
            challenger_model_id=challenger_model_id,
            start_timestamp=str(eval_timestamps[0]),
            end_timestamp=str(eval_timestamps[-1]),
            total_bars=n_timestamps,
            total_rebalances=n_rebal,
            total_predictions_evaluated=len(all_champ_probs),
            mean_directional_agreement=round(dir_agr_rate, 4),
            mean_selection_jaccard=round(mean_jaccard, 4),
            prediction_correlation=round(prob_corr, 4),
            probability_correlation=round(prob_corr, 4),
            champion_gross_return_pct=round((champ_equity - 1.0 + sum(obs.champion_cost for obs in observations)) * 100.0, 2),
            challenger_gross_return_pct=round((chall_equity - 1.0 + sum(obs.challenger_cost for obs in observations)) * 100.0, 2),
            champion_net_return_pct=round((champ_equity - 1.0) * 100.0, 2),
            challenger_net_return_pct=round((chall_equity - 1.0) * 100.0, 2),
            champion_net_sharpe=round(champ_sharpe, 2),
            challenger_net_sharpe=round(chall_sharpe, 2),
            champion_max_drawdown_pct=round(champ_max_dd, 2),
            challenger_max_drawdown_pct=round(chall_max_dd, 2),
            champion_total_turnover=round(float(sum(obs.champion_turnover for obs in observations)), 2),
            challenger_total_turnover=round(float(sum(obs.challenger_turnover for obs in observations)), 2),
            champion_total_cost_pct=round(float(sum(obs.champion_cost for obs in observations)) * 100.0, 3),
            challenger_total_cost_pct=round(float(sum(obs.challenger_cost for obs in observations)) * 100.0, 3),
            champion_p50_latency_ms=round(float(np.percentile(champ_latencies, 50)), 3),
            challenger_p50_latency_ms=round(float(np.percentile(chall_latencies, 50)), 3),
            champion_p95_latency_ms=round(float(np.percentile(champ_latencies, 95)), 3),
            challenger_p95_latency_ms=round(float(np.percentile(chall_latencies, 95)), 3),
            error_count=errors,
            is_shadow_isolated=True,
            observations=observations
        )
