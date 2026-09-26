"""
Anti-Leakage Framework: Embargo Gap Enforcement
Verifies that walk-forward splits maintain an embargo buffer to eliminate serial correlation bleed.
"""
import pytest
import pandas as pd
import numpy as np
from data.splitting import TemporalSplitter


def test_embargo_gap_maintained_between_train_and_val():
    dates = pd.date_range("2024-01-01", periods=1200, freq="1h", tz="UTC")
    df = pd.DataFrame({"close": np.arange(1200)}, index=dates)

    splits = TemporalSplitter.purged_walk_forward_split(df, n_splits=5, embargo_pct=0.02)
    assert len(splits) == 5

    for fold_idx, (train_fold, test_fold, meta) in enumerate(splits, 1):
        assert len(train_fold) > 0
        assert len(test_fold) > 0
        assert train_fold.index.max() < test_fold.index.min()
        assert meta["embargo_bars"] > 0
        
        embargo_gap_hours = (test_fold.index.min() - train_fold.index.max()).total_seconds() / 3600.0
        assert embargo_gap_hours > meta["embargo_bars"], f"Fold {fold_idx}: Embargo buffer violated"
