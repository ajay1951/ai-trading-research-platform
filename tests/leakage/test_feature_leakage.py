"""
Anti-Leakage Framework: Feature Leakage Prevention
Verifies that features are computed using only past and current windows.
"""
import pytest
import numpy as np
import pandas as pd
from features.technical import TechnicalFeaturePipeline


def test_feature_window_causality():
    np.random.seed(123)
    n_bars = 100
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "open": 100 + np.cumsum(np.random.randn(n_bars)),
        "high": 102 + np.cumsum(np.random.randn(n_bars)),
        "low": 98 + np.cumsum(np.random.randn(n_bars)),
        "close": 101 + np.cumsum(np.random.randn(n_bars)),
        "volume": np.random.uniform(500, 1500, size=n_bars)
    }, index=dates)

    pipeline = TechnicalFeaturePipeline()
    features = pipeline.transform(df, dropna=False)

    # First bar cannot have rolling return or rolling std with window > 1 without being NaN
    assert np.isnan(features["return_1"].iloc[0])
    assert np.isnan(features["return_24"].iloc[0])
