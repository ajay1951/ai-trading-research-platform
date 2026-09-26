"""
Leakage Prevention Test: Feature Scaler & Normalizer Leakage
============================================================
Verifies that scaling parameters (mean, std, min, max) are fitted strictly
on the training dataset fold and never contaminated by validation/test distributions.
"""

import pytest
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from data.splitting import TemporalSplitter


def test_scaler_fitted_only_on_train():
    """
    Test: Scaler must be fit strictly on train split.
    Validation/Test data must NOT influence the scaling parameters.
    """
    np.random.seed(42)
    n = 1000
    dates = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    
    # Train data has mean ~10, Test data has a market shift to mean ~50
    train_vals = np.random.normal(loc=10.0, scale=2.0, size=700)
    val_vals = np.random.normal(loc=20.0, scale=2.0, size=150)
    test_vals = np.random.normal(loc=50.0, scale=5.0, size=150)
    all_vals = np.concatenate([train_vals, val_vals, test_vals])

    df = pd.DataFrame({"timestamp": dates, "feature_1": all_vals}).set_index("timestamp")

    train_df, val_df, test_df = TemporalSplitter.chronological_split(df, 0.7, 0.15, 0.15)

    # Correct methodology: fit scaler ONLY on train
    scaler_correct = StandardScaler()
    scaler_correct.fit(train_df[["feature_1"]])

    # Assert scaler mean reflects ONLY the training distribution (approx 10.0)
    assert np.isclose(scaler_correct.mean_[0], 10.0, atol=0.5), (
        f"Expected train mean ~10.0, got {scaler_correct.mean_[0]}"
    )

    # Flawed methodology (leakage): fitting on entire dataset
    scaler_leaked = StandardScaler()
    scaler_leaked.fit(df[["feature_1"]])

    # Assert that the leaked scaler mean is significantly corrupted by future data
    assert abs(scaler_leaked.mean_[0] - scaler_correct.mean_[0]) > 5.0, (
        "Dataset shift detection failed in test setup"
    )

    # Ensure transforming test_df with train-fitted scaler does not change scaler parameters
    _ = scaler_correct.transform(test_df[["feature_1"]])
    assert np.isclose(scaler_correct.mean_[0], 10.0, atol=0.5)
