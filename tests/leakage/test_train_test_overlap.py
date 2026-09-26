"""
Anti-Leakage Framework: Train-Test Overlap Prevention
Verifies that train, validation, and test datasets have zero overlap and strict chronological ordering.
"""
import pytest
import pandas as pd
import numpy as np
from data.splitting import TemporalSplitter


def test_train_test_splits_have_zero_overlap():
    dates = pd.date_range("2026-01-01", periods=1000, freq="1h", tz="UTC")
    df = pd.DataFrame({"close": np.arange(1000)}, index=dates)

    train_df, val_df, test_df = TemporalSplitter.chronological_split(df, 0.70, 0.15, 0.15, embargo_bars=5)

    train_set = set(train_df.index)
    val_set = set(val_df.index)
    test_set = set(test_df.index)

    # Empty intersections
    assert len(train_set.intersection(val_set)) == 0, "Train and Validation sets overlap!"
    assert len(train_set.intersection(test_set)) == 0, "Train and Test sets overlap!"
    assert len(val_set.intersection(test_set)) == 0, "Validation and Test sets overlap!"

    # Monotonic time boundary assertion
    assert train_df.index.max() < val_df.index.min()
    assert val_df.index.max() < test_df.index.min()
