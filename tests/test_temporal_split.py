"""
Leakage Prevention Test: Temporal Split Integrity
=================================================
Verifies that chronological splits maintain strict time boundaries,
zero overlap, and enforced embargo periods.
"""

import pytest
import numpy as np
import pandas as pd
from data.splitting import TemporalSplitter


def test_chronological_split_no_overlap():
    """
    Test: Train, Val, and Test must have zero overlap and strict chronological ordering.
    """
    dates = pd.date_range("2024-01-01", periods=1000, freq="1h", tz="UTC")
    df = pd.DataFrame({"close": np.arange(1000)}, index=dates)

    train_df, val_df, test_df = TemporalSplitter.chronological_split(df, 0.70, 0.15, 0.15, embargo_bars=5)

    assert len(train_df) == 700
    assert len(val_df) == 150
    assert len(test_df) == 140 # 150 - 2*5 embargo bars

    # Time boundaries check
    assert train_df.index.max() < val_df.index.min(), "Train max timestamp must be strictly before Val min timestamp"
    assert val_df.index.max() < test_df.index.min(), "Val max timestamp must be strictly before Test min timestamp"

    # Embargo buffer check
    train_to_val_gap = (val_df.index.min() - train_df.index.max()).total_seconds() / 3600.0
    val_to_test_gap = (test_df.index.min() - val_df.index.max()).total_seconds() / 3600.0
    
    # 5 embargo bars + 1 regular step = 6 hours gap
    assert train_to_val_gap >= 6.0, f"Expected >= 6h gap with 5 embargo bars, got {train_to_val_gap}h"
    assert val_to_test_gap >= 6.0, f"Expected >= 6h gap with 5 embargo bars, got {val_to_test_gap}h"


def test_purged_walk_forward_splits():
    """
    Test: Purged walk-forward folds have zero forward contamination and positive embargo.
    """
    dates = pd.date_range("2024-01-01", periods=1200, freq="1h", tz="UTC")
    df = pd.DataFrame({"close": np.arange(1200)}, index=dates)

    splits = TemporalSplitter.purged_walk_forward_split(df, n_splits=5, embargo_pct=0.02)
    assert len(splits) == 5

    for fold_idx, (train_fold, test_fold, meta) in enumerate(splits, 1):
        assert len(train_fold) > 0
        assert len(test_fold) > 0
        assert train_fold.index.max() < test_fold.index.min(), f"Fold {fold_idx}: Train end must precede Test start"
        
        # Test fold size should be consistent
        assert meta["embargo_bars"] > 0
        embargo_gap_hours = (test_fold.index.min() - train_fold.index.max()).total_seconds() / 3600.0
        assert embargo_gap_hours > meta["embargo_bars"], f"Fold {fold_idx}: Embargo buffer violated"
