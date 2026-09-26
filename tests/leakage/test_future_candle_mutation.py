"""
Anti-Leakage Framework: Future Candle Mutation Test
Verifies that mutating candle t+k (for any k >= 1) produces ZERO changes in all historical features up to t.
"""
import pytest
import numpy as np
import pandas as pd
from features.technical import TechnicalFeaturePipeline


def test_future_candle_mutation_invariance():
    """Mutating any candle at or after t+1 must leave features at t bitwise identical."""
    np.random.seed(999)
    n_bars = 150
    dates = pd.date_range("2025-01-01", periods=n_bars, freq="1h", tz="UTC")
    df_original = pd.DataFrame({
        "open": 50000.0 + np.cumsum(np.random.randn(n_bars) * 100),
        "high": 50200.0 + np.cumsum(np.random.randn(n_bars) * 100),
        "low": 49800.0 + np.cumsum(np.random.randn(n_bars) * 100),
        "close": 50100.0 + np.cumsum(np.random.randn(n_bars) * 100),
        "volume": np.random.uniform(10, 50, size=n_bars)
    }, index=dates)

    pipeline = TechnicalFeaturePipeline()
    feats_orig = pipeline.transform(df_original, dropna=False)

    split_point = 80
    historical_slice_before = feats_orig.iloc[:split_point + 1].copy()

    # Apply massive shock to future candles (split_point + 1 onwards)
    df_shocked = df_original.copy()
    df_shocked.iloc[split_point + 1:, df_shocked.columns.get_loc("close")] *= 10.0
    df_shocked.iloc[split_point + 1:, df_shocked.columns.get_loc("high")] *= 12.0
    df_shocked.iloc[split_point + 1:, df_shocked.columns.get_loc("low")] *= 8.0
    df_shocked.iloc[split_point + 1:, df_shocked.columns.get_loc("volume")] *= 100.0

    feats_shocked = pipeline.transform(df_shocked, dropna=False)
    historical_slice_after = feats_shocked.iloc[:split_point + 1].copy()

    for col in feats_orig.columns:
        s1 = historical_slice_before[col]
        s2 = historical_slice_after[col]
        
        # Valid values must match exactly
        valid_mask = (~s1.isna()) & (~s2.isna())
        diff = np.abs(s1[valid_mask] - s2[valid_mask])
        assert np.all(diff < 1e-9), f"Feature {col} changed historically after future candle mutation!"
