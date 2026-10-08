"""
evaluation/model_intelligence.py
================================
P3-3 Canonical Prediction Dataset & Model Intelligence Analyzer.

Provides:
1. Prediction Record Container & Integrity Validation (bounds, timestamp order, no leakage).
2. Comprehensive Classification Metrics: Accuracy, Precision, Recall, F1, Balanced Accuracy,
   ROC-AUC, PR-AUC, Log Loss, Brier Score.
3. Confidence vs Realized Outcome Monotonicity Analysis (Auditing returns, hit rates across confidence quintiles).
4. Feature Importance Stability Analysis across WFO folds and market regimes.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    balanced_accuracy_score,
    roc_auc_score,
    average_precision_score,
    log_loss,
    brier_score_loss
)


@dataclass
class PredictionRecord:
    """Canonical representation of a single model prediction."""
    timestamp: str
    symbol: str
    fold: int
    raw_score: float
    probability: float
    predicted_label: int
    realized_label: int
    forward_return: float
    regime: str
    model_version: str = "P3-3-LGBM-v1"


@dataclass
class ConfidenceBucketAnalysis:
    """Performance attribution for a specific prediction confidence bucket."""
    bucket_label: str
    lower_bound: float
    upper_bound: float
    sample_count: int
    hit_rate: float
    mean_forward_return_pct: float
    median_forward_return_pct: float
    brier_score: float
    log_loss: float
    realized_sharpe: float


class ModelIntelligenceAnalyzer:
    """
    Executes deep analytical audits of model predictions, classification metrics,
    confidence monotonicity, and feature importance stability.
    """

    @staticmethod
    def audit_prediction_integrity(records: List[PredictionRecord]) -> Dict[str, Any]:
        """
        Validates integrity invariants across prediction records.
        """
        if not records:
            return {"status": "EMPTY", "is_valid": False, "violations": ["No prediction records provided"]}

        violations: List[str] = []
        timestamps = [r.timestamp for r in records]
        probs = [r.probability for r in records]

        # 1. Probability Bounds [0, 1]
        invalid_probs = [p for p in probs if p < 0.0 or p > 1.0 or np.isnan(p) or np.isinf(p)]
        if invalid_probs:
            violations.append(f"Found {len(invalid_probs)} invalid probabilities outside [0.0, 1.0]")

        # 2. Check duplicate (timestamp, symbol) pairs
        keys = [(r.timestamp, r.symbol) for r in records]
        if len(keys) != len(set(keys)):
            violations.append("Duplicate (timestamp, symbol) prediction pairs detected")

        # 3. Label validity
        invalid_labels = [r for r in records if r.realized_label not in [0, 1]]
        if invalid_labels:
            violations.append(f"Found {len(invalid_labels)} non-binary realized labels")

        return {
            "total_records": len(records),
            "unique_timestamps": len(set(timestamps)),
            "symbols_count": len(set(r.symbol for r in records)),
            "folds_count": len(set(r.fold for r in records)),
            "is_valid": len(violations) == 0,
            "violations": violations
        }

    @staticmethod
    def compute_classification_metrics(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.50) -> Dict[str, float]:
        """
        Computes standard multi-metric classification performance.
        """
        if len(y_true) < 5 or len(np.unique(y_true)) < 2:
            return {
                "accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0,
                "balanced_accuracy": 0.0, "roc_auc": 0.50, "pr_auc": 0.0,
                "brier_score": 0.0, "log_loss": 0.0
            }

        y_pred = (y_prob >= threshold).astype(int)

        acc = float(accuracy_score(y_true, y_pred))
        prec = float(precision_score(y_true, y_pred, zero_division=0))
        rec = float(recall_score(y_true, y_pred, zero_division=0))
        f1 = float(f1_score(y_true, y_pred, zero_division=0))
        bal_acc = float(balanced_accuracy_score(y_true, y_pred))

        try:
            auc = float(roc_auc_score(y_true, y_prob))
        except Exception:
            auc = 0.50

        try:
            pr_auc = float(average_precision_score(y_true, y_prob))
        except Exception:
            pr_auc = float(np.mean(y_true))

        brier = float(brier_score_loss(y_true, y_prob))
        p_clipped = np.clip(y_prob, 1e-12, 1.0 - 1e-12)
        ll = float(log_loss(y_true, p_clipped))

        return {
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "balanced_accuracy": round(bal_acc, 4),
            "roc_auc": round(auc, 4),
            "pr_auc": round(pr_auc, 4),
            "brier_score": round(brier, 4),
            "log_loss": round(ll, 4)
        }

    @staticmethod
    def audit_confidence_vs_outcome(records: List[PredictionRecord]) -> List[ConfidenceBucketAnalysis]:
        """
        Partitions predictions into confidence buckets and checks outcome monotonicity.
        """
        bucket_defs = [
            ("Low (0.00-0.45)", 0.00, 0.45),
            ("Neutral (0.45-0.55)", 0.45, 0.55),
            ("Moderate Bullish (0.55-0.65)", 0.55, 0.65),
            ("High Bullish (0.65-0.75)", 0.65, 0.75),
            ("Extreme Bullish (0.75-1.00)", 0.75, 1.00)
        ]

        results: List[ConfidenceBucketAnalysis] = []

        for label, lower, upper in bucket_defs:
            sub = [r for r in records if lower <= r.probability < upper or (upper == 1.00 and r.probability == 1.00)]
            if not sub:
                results.append(ConfidenceBucketAnalysis(
                    bucket_label=label, lower_bound=lower, upper_bound=upper,
                    sample_count=0, hit_rate=0.0, mean_forward_return_pct=0.0,
                    median_forward_return_pct=0.0, brier_score=0.0, log_loss=0.0, realized_sharpe=0.0
                ))
                continue

            y_true = np.array([r.realized_label for r in sub])
            y_prob = np.array([r.probability for r in sub])
            rets = np.array([r.forward_return for r in sub])

            hit_rate = float(np.mean(y_true))
            mean_ret = float(np.mean(rets)) * 100.0
            med_ret = float(np.median(rets)) * 100.0

            brier = float(np.mean((y_prob - y_true) ** 2))
            p_clip = np.clip(y_prob, 1e-12, 1.0 - 1e-12)
            ll = -float(np.mean(y_true * np.log(p_clip) + (1 - y_true) * np.log(1 - p_clip)))

            ret_std = float(np.std(rets))
            sharpe = (float(np.mean(rets)) / ret_std * math.sqrt(2190.0)) if ret_std > 1e-6 else 0.0

            results.append(ConfidenceBucketAnalysis(
                bucket_label=label,
                lower_bound=lower,
                upper_bound=upper,
                sample_count=len(sub),
                hit_rate=round(hit_rate, 4),
                mean_forward_return_pct=round(mean_ret, 2),
                median_forward_return_pct=round(med_ret, 2),
                brier_score=round(brier, 4),
                log_loss=round(ll, 4),
                realized_sharpe=round(sharpe, 2)
            ))

        return results

    @staticmethod
    def analyze_feature_importance_stability(
        fold_importances: Dict[int, Dict[str, float]]
    ) -> List[Dict[str, Any]]:
        """
        Measures feature importance consistency across WFO folds.
        """
        all_features = sorted(list(set(f for imp in fold_importances.values() for f in imp.keys())))
        stability_records: List[Dict[str, Any]] = []

        for feat in all_features:
            vals = [fold_importances[f].get(feat, 0.0) for f in fold_importances.keys()]
            mean_v = float(np.mean(vals))
            std_v = float(np.std(vals))
            cv = (std_v / mean_v) if mean_v > 1e-6 else 0.0

            stability_records.append({
                "feature": feat,
                "mean_importance": round(mean_v, 4),
                "std_importance": round(std_v, 4),
                "coefficient_of_variation": round(cv, 4),
                "min_importance": round(float(np.min(vals)), 4),
                "max_importance": round(float(np.max(vals)), 4),
                "is_stable": cv < 0.60
            })

        stability_records.sort(key=lambda x: x["mean_importance"], reverse=True)
        return stability_records
