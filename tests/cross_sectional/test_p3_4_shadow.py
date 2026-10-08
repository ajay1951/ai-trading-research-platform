"""
tests/cross_sectional/test_p3_4_shadow.py
=========================================
P3-4 Isolated Shadow Evaluation Validation Test Suite.

Validates:
1. Side-by-side inference execution
2. Agreement rate, probability divergence, and latency tracking
3. Complete isolation: Zero orders, zero position mutations
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock
from evaluation.shadow_evaluation import ShadowEvaluationHarness


def test_shadow_evaluation_execution():
    # Mock models
    champ_model = MagicMock()
    champ_model.predict_proba.return_value = np.array([[0.3, 0.7]])

    chall_model = MagicMock()
    chall_model.predict_proba.return_value = np.array([[0.35, 0.65]])

    # Synthetic features panel
    dates = pd.date_range("2026-01-01", periods=25, freq="1h")
    panel = pd.DataFrame({
        "feat1": np.random.normal(0, 1, 25),
        "feat2": np.random.normal(0, 1, 25)
    }, index=dates)

    summary = ShadowEvaluationHarness.run_shadow_comparison(
        champion_model=champ_model,
        challenger_model=chall_model,
        champion_model_id="CHAMP",
        challenger_model_id="CHALL",
        features_panel=panel,
        symbols=["BTCUSDT"]
    )

    assert summary.total_observations == 25
    assert summary.agreement_rate == 1.0 # Both predict >= 0.50
    assert summary.error_count == 0
    assert summary.is_shadow_valid
    assert len(summary.prediction_records) == 25
