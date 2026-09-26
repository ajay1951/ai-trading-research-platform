"""
Anti-Leakage Framework: Target/Label Leakage Prevention
Verifies that future labels (forward returns, future targets) are strictly excluded from feature space.
"""
import pytest
import numpy as np
import pandas as pd
from features.technical import TechnicalFeaturePipeline


def test_label_not_in_feature_columns():
    forbidden_substrings = ["future", "target", "label", "lead", "fwd", "next_"]
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
