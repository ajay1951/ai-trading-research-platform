"""
evaluation/shadow_evaluation.py
===============================
P3-4 Isolated Shadow Evaluation Harness.

Provides:
1. Side-by-Side Model Evaluation (Champion vs Challenger).
2. Complete Execution Isolation (Zero order execution, zero portfolio mutation).
3. Prediction Agreement, Confidence Divergence & Decision Latency Profiling.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class ShadowPredictionRecord:
    """Single point-in-time shadow prediction pair."""
    timestamp: str
    symbol: str
    champion_probability: float
    challenger_probability: float
    prediction_agreement: bool # Both agree on >= 0.50 direction
    probability_diff: float
    champion_latency_ms: float
    challenger_latency_ms: float


@dataclass
class ShadowRunSummary:
    """Aggregated results from a shadow evaluation period."""
    champion_model_id: str
    challenger_model_id: str
    total_observations: int
    agreement_rate: float
    mean_absolute_prob_diff: float
    correlation: float
    champion_avg_latency_ms: float
    challenger_avg_latency_ms: float
    error_count: int
    is_shadow_valid: bool
    prediction_records: List[ShadowPredictionRecord] = field(default_factory=list)


class ShadowEvaluationHarness:
    """
    Executes isolated, non-interfering shadow prediction runs.
    """

    @staticmethod
    def run_shadow_comparison(
        champion_model: Any,
        challenger_model: Any,
        champion_model_id: str,
        challenger_model_id: str,
        features_panel: pd.DataFrame,
        symbols: List[str]
    ) -> ShadowRunSummary:
        """
        Runs both models on identical historical/live feature frames and computes divergence.
        """
        records: List[ShadowPredictionRecord] = []
        errors = 0

        for ts in features_panel.index:
            row = features_panel.loc[ts]
            f_cols = [c for c in row.index if c not in ['timestamp', 'target', 'open', 'high', 'low', 'close', 'quote_volume']]
            f_vec = row[f_cols].values.reshape(1, -1)

            # Champion Inference
            t0 = time.perf_counter()
            try:
                p_champ = float(champion_model.predict_proba(f_vec)[0, 1])
            except Exception:
                p_champ = 0.50
                errors += 1
            lat_champ = (time.perf_counter() - t0) * 1000.0

            # Challenger Inference
            t1 = time.perf_counter()
            try:
                p_chall = float(challenger_model.predict_proba(f_vec)[0, 1])
            except Exception:
                p_chall = 0.50
                errors += 1
            lat_chall = (time.perf_counter() - t1) * 1000.0

            agree = (p_champ >= 0.50) == (p_chall >= 0.50)
            p_diff = abs(p_champ - p_chall)

            records.append(ShadowPredictionRecord(
                timestamp=str(ts),
                symbol=symbols[0] if symbols else "PORTFOLIO",
                champion_probability=round(p_champ, 4),
                challenger_probability=round(p_chall, 4),
                prediction_agreement=agree,
                probability_diff=round(p_diff, 4),
                champion_latency_ms=round(lat_champ, 3),
                challenger_latency_ms=round(lat_chall, 3)
            ))

        if not records:
            return ShadowRunSummary(
                champion_model_id=champion_model_id,
                challenger_model_id=challenger_model_id,
                total_observations=0,
                agreement_rate=0.0,
                mean_absolute_prob_diff=0.0,
                correlation=1.0,
                champion_avg_latency_ms=0.0,
                challenger_avg_latency_ms=0.0,
                error_count=errors,
                is_shadow_valid=False
            )

        n = len(records)
        agreements = sum(1 for r in records if r.prediction_agreement)
        agr_rate = agreements / n
        mean_diff = float(np.mean([r.probability_diff for r in records]))

        c_probs = np.array([r.champion_probability for r in records])
        ch_probs = np.array([r.challenger_probability for r in records])
        std_c, std_ch = float(np.std(c_probs)), float(np.std(ch_probs))
        if std_c > 1e-6 and std_ch > 1e-6:
            corr = float(np.corrcoef(c_probs, ch_probs)[0, 1])
        else:
            corr = 1.0

        avg_lat_c = float(np.mean([r.champion_latency_ms for r in records]))
        avg_lat_ch = float(np.mean([r.challenger_latency_ms for r in records]))

        return ShadowRunSummary(
            champion_model_id=champion_model_id,
            challenger_model_id=challenger_model_id,
            total_observations=n,
            agreement_rate=round(agr_rate, 4),
            mean_absolute_prob_diff=round(mean_diff, 4),
            correlation=round(corr, 4),
            champion_avg_latency_ms=round(avg_lat_c, 3),
            challenger_avg_latency_ms=round(avg_lat_ch, 3),
            error_count=errors,
            is_shadow_valid=(n >= 20 and errors == 0),
            prediction_records=records
        )
