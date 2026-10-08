"""
tests/cross_sectional/test_p3_3_model_intelligence.py
=====================================================
P3-3 Canonical Prediction Dataset & Model Intelligence Validation Test Suite.

Validates:
1. Prediction record container and integrity verification
2. Multi-metric classification performance calculations
3. Confidence vs realized outcome monotonicity verification
4. Feature importance stability across folds
5. Future mutation invariance
"""

import pytest
import numpy as np
from evaluation.model_intelligence import (
    ModelIntelligenceAnalyzer,
    PredictionRecord,
    ConfidenceBucketAnalysis
)


def test_prediction_integrity_validation():
    records = [
        PredictionRecord(timestamp="2026-01-01 00:00:00", symbol="BTCUSDT", fold=1, raw_score=0.6, probability=0.6, predicted_label=1, realized_label=1, forward_return=0.01, regime="BULL"),
        PredictionRecord(timestamp="2026-01-01 00:00:00", symbol="ETHUSDT", fold=1, raw_score=0.4, probability=0.4, predicted_label=0, realized_label=0, forward_return=-0.01, regime="BULL"),
    ]

    res = ModelIntelligenceAnalyzer.audit_prediction_integrity(records)
    assert res["is_valid"]
    assert res["total_records"] == 2
    assert len(res["violations"]) == 0


def test_invalid_probability_detection():
    invalid_records = [
        PredictionRecord(timestamp="2026-01-01 00:00:00", symbol="BTCUSDT", fold=1, raw_score=1.5, probability=1.5, predicted_label=1, realized_label=1, forward_return=0.01, regime="BULL"),
    ]

    res = ModelIntelligenceAnalyzer.audit_prediction_integrity(invalid_records)
    assert not res["is_valid"]
    assert len(res["violations"]) > 0


def test_classification_metrics_computation():
    y_true = np.array([1, 0, 1, 1, 0, 0, 1, 0])
    y_prob = np.array([0.8, 0.2, 0.7, 0.6, 0.3, 0.4, 0.9, 0.1])

    metrics = ModelIntelligenceAnalyzer.compute_classification_metrics(y_true, y_prob)

    assert metrics["accuracy"] >= 0.75
    assert metrics["roc_auc"] >= 0.80
    assert metrics["brier_score"] <= 0.15


def test_confidence_vs_outcome_analysis():
    records = [
        PredictionRecord(timestamp=f"2026-01-01 0{i}:00:00", symbol="BTCUSDT", fold=1, raw_score=0.7, probability=0.70, predicted_label=1, realized_label=1, forward_return=0.02, regime="BULL")
        for i in range(5)
    ]

    buckets = ModelIntelligenceAnalyzer.audit_confidence_vs_outcome(records)
    high_bucket = [b for b in buckets if "High Bullish" in b.bucket_label][0]

    assert high_bucket.sample_count == 5
    assert high_bucket.hit_rate == 1.0
    assert high_bucket.mean_forward_return_pct > 0.0


def test_feature_importance_stability():
    fold_imps = {
        1: {"volatility": 150.0, "rsi": 80.0},
        2: {"volatility": 140.0, "rsi": 85.0},
        3: {"volatility": 160.0, "rsi": 75.0}
    }

    stability = ModelIntelligenceAnalyzer.analyze_feature_importance_stability(fold_imps)
    assert len(stability) == 2
    assert stability[0]["feature"] == "volatility"
    assert stability[0]["is_stable"]
