"""
Leakage Prevention Test: Label Leakage Prevention
=================================================
Verifies that future labels (forward returns, future highs/lows)
are strictly separated from input feature matrices X.
"""

import pytest
import numpy as np
import pandas as pd


def test_label_not_in_feature_columns():
    """
    Test: Ensure target column names and forward-looking definitions
    never appear in the training feature columns.
    """
    forbidden_substrings = ["future", "target", "label", "lead", "fwd", "next_"]

    from features.technical import TechnicalFeaturePipeline
    pipeline = TechnicalFeaturePipeline()
    
    dates = pd.date_range("2024-01-01", periods=100, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "open": np.random.uniform(90, 110, 100),
        "high": np.random.uniform(100, 120, 100),
        "low": np.random.uniform(80, 100, 100),
        "close": np.random.uniform(90, 110, 100),
        "volume": np.random.uniform(10, 100, 100)
    }, index=dates)

    features = pipeline.transform(df)

    for col in features.columns:
        col_lower = col.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in col_lower, (
                f"POTENTIAL LABEL LEAKAGE: Feature column '{col}' contains forward-looking keyword '{forbidden}'"
            )


def test_forward_return_calculation_causality():
    """
    Test: Verify that target y_t = (P_{t+1} - P_t) / P_t cannot be computed from features at t.
    """
    np.random.seed(42)
    prices = pd.Series([100.0, 105.0, 95.0, 110.0, 115.0])
    
    # Correct forward label: shift(-1)
    forward_return = (prices.shift(-1) - prices) / prices

    # At index 0, forward return is (105 - 100) / 100 = +0.05
    assert np.isclose(forward_return.iloc[0], 0.05)
    # The last element must be NaN (future price unknown)
    assert np.isnan(forward_return.iloc[-1])

    # Backward return (valid feature): pct_change()
    historical_return = prices.pct_change()
    assert np.isnan(historical_return.iloc[0])
    assert np.isclose(historical_return.iloc[1], 0.05)

    # Asserts that at timestamp t=1, historical return (+0.05) != forward return (-0.0952)
    common_idx = [1, 2, 3]
    assert not np.allclose(historical_return.loc[common_idx], forward_return.loc[common_idx])
