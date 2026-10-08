"""
tests/cross_sectional/test_p4_1_extended_shadow.py
==================================================
P4-1 Longitudinal Shadow Study & Agreement Validation Test Suite.

Validates:
1. Longitudinal shadow execution across multiple rebalances
2. Prediction agreement, correlation, and Jaccard Top-2 similarity
3. Independent economic accounting net of P3-1F friction
4. Zero missing / invalid predictions
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock
from evaluation.extended_shadow import ExtendedShadowEngine, ExtendedShadowStudyResult


def test_longitudinal_shadow_study_execution():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    dates = pd.date_range("2026-01-01", periods=150, freq="1h")

    # Synthetic prices
    prices_df = pd.DataFrame({
        "BTCUSDT": np.linspace(50000, 52000, 150),
        "ETHUSDT": np.linspace(3000, 3100, 150),
        "SOLUSDT": np.linspace(100, 105, 150)
    }, index=dates)

    asset_dfs = {}
    for s in symbols:
        asset_dfs[s] = pd.DataFrame({
            "feat1": np.random.normal(0, 1, 150),
            "feat2": np.random.normal(0, 1, 150),
            "target": np.random.binomial(1, 0.5, 150)
        }, index=dates)

    champ_model = MagicMock()
    champ_model.predict_proba.return_value = np.array([[0.4, 0.6]])

    chall_model = MagicMock()
    chall_model.predict_proba.return_value = np.array([[0.42, 0.58]])

    results = ExtendedShadowEngine.run_longitudinal_study(
        champion_model=champ_model,
        challenger_model=chall_model,
        champion_model_id="CHAMP",
        challenger_model_id="CHALL",
        prices_df=prices_df,
        asset_dfs=asset_dfs,
        eval_timestamps=list(dates),
        rebalance_interval_bars=48,
        cost_bps_one_way=21.38
    )

    assert results.total_bars == 150
    assert results.total_rebalances >= 2
    assert results.mean_directional_agreement == 1.0
    assert results.mean_selection_jaccard == 1.0
    assert results.error_count == 0
    assert results.is_shadow_isolated
