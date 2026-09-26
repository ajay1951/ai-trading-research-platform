"""
Leakage Prevention Test: No Lookahead Bias in Features
======================================================
Verifies that modifying future price data (at t+1 or beyond) has ZERO effect
on features calculated at timestamp t.
"""

import pytest
import numpy as np
import pandas as pd
from features.technical import TechnicalFeaturePipeline


def generate_synthetic_ohlcv(n_bars: int = 200) -> pd.DataFrame:
    """Generates synthetic random walk OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1h", tz="UTC")
    returns = np.random.normal(0, 0.01, size=n_bars)
    close = 100.0 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.normal(0, 0.005, size=n_bars)))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, size=n_bars)))
    open_p = (high + low) / 2.0
    volume = np.random.uniform(100, 1000, size=n_bars)

    df = pd.DataFrame({
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    }, index=dates)
    return df


def test_features_have_no_lookahead():
    """
    Test: Modifying future candles MUST NOT change features at time t.
    """
    df_base = generate_synthetic_ohlcv(200)
    pipeline = TechnicalFeaturePipeline()
    features_base = pipeline.transform(df_base, dropna=False)

    eval_idx = 100
    base_values_at_t = features_base.iloc[eval_idx].copy()

    # Create mutated future dataset: alter all prices after eval_idx
    df_mutated = df_base.copy()
    df_mutated.iloc[eval_idx + 1:, df_mutated.columns.get_loc("close")] *= 5.0
    df_mutated.iloc[eval_idx + 1:, df_mutated.columns.get_loc("high")] *= 6.0
    df_mutated.iloc[eval_idx + 1:, df_mutated.columns.get_loc("low")] *= 4.0
    df_mutated.iloc[eval_idx + 1:, df_mutated.columns.get_loc("volume")] *= 10.0

    features_mutated = pipeline.transform(df_mutated, dropna=False)
    mutated_values_at_t = features_mutated.iloc[eval_idx].copy()

    # Compare features at eval_idx
    for col in features_base.columns:
        val_base = base_values_at_t[col]
        val_mut = mutated_values_at_t[col]
        if np.isnan(val_base) and np.isnan(val_mut):
            continue
        assert np.isclose(val_base, val_mut, rtol=1e-5, atol=1e-8), (
            f"LOOKAHEAD LEAK DETECTED in feature '{col}' at index {eval_idx}: "
            f"Original={val_base}, Mutated Future={val_mut}"
        )
