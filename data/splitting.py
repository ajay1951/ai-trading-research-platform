"""
Quantitative Research: Temporal Dataset Splitting
=================================================
Strict temporal splitting to eliminate lookahead bias and serial correlation leakage:
- Chronological Train / Validation / Test
- Expanding Window (Anchor-start)
- Rolling Window (Fixed lookback)
- Purged & Embargoed Cross-Validation (De Prado methodology)
"""

from typing import Tuple, List, Generator, Dict, Any
import pandas as pd
import numpy as np


class TemporalSplitter:
    """
    Provides time-series splitting utilities with strict boundary discipline and embargo buffering.
    """

    @staticmethod
    def chronological_split(
        df: pd.DataFrame,
        train_pct: float = 0.70,
        val_pct: float = 0.15,
        test_pct: float = 0.15,
        embargo_bars: int = 0
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Splits dataset chronologically into Train, Validation, and Test sets.
        Ensures: Train End + Embargo <= Val Start, Val End + Embargo <= Test Start.
        """
        assert abs((train_pct + val_pct + test_pct) - 1.0) < 1e-5, "Percentages must sum to 1.0"
        n = len(df)
        
        train_end_idx = int(n * train_pct)
        val_start_idx = train_end_idx + embargo_bars
        val_end_idx = val_start_idx + int(n * val_pct)
        test_start_idx = val_end_idx + embargo_bars

        train_df = df.iloc[:train_end_idx].copy()
        val_df = df.iloc[val_start_idx:val_end_idx].copy()
        test_df = df.iloc[test_start_idx:].copy()

        return train_df, val_df, test_df

    @staticmethod
    def expanding_window_split(
        df: pd.DataFrame,
        initial_train_bars: int,
        test_bars: int,
        step_bars: int,
        embargo_bars: int = 0
    ) -> Generator[Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]], None, None]:
        """
        Yields (train_df, test_df, metadata) with an expanding training window.
        Train window grows on each iteration: [0 : t], Test: [t + embargo : t + embargo + test_bars].
        """
        n = len(df)
        t = initial_train_bars
        split_id = 0

        while t + embargo_bars + test_bars <= n:
            train_df = df.iloc[:t].copy()
            test_start = t + embargo_bars
            test_df = df.iloc[test_start : test_start + test_bars].copy()
            
            meta = {
                "split_id": split_id,
                "train_start_idx": 0,
                "train_end_idx": t,
                "test_start_idx": test_start,
                "test_end_idx": test_start + test_bars,
                "embargo_bars": embargo_bars,
                "train_len": len(train_df),
                "test_len": len(test_df)
            }
            yield train_df, test_df, meta
            t += step_bars
            split_id += 1

    @staticmethod
    def rolling_window_split(
        df: pd.DataFrame,
        train_bars: int,
        test_bars: int,
        step_bars: int,
        embargo_bars: int = 0
    ) -> Generator[Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]], None, None]:
        """
        Yields (train_df, test_df, metadata) with a fixed-size rolling training window.
        Train: [t - train_bars : t], Test: [t + embargo : t + embargo + test_bars].
        """
        n = len(df)
        t = train_bars
        split_id = 0

        while t + embargo_bars + test_bars <= n:
            train_start = t - train_bars
            train_df = df.iloc[train_start : t].copy()
            test_start = t + embargo_bars
            test_df = df.iloc[test_start : test_start + test_bars].copy()

            meta = {
                "split_id": split_id,
                "train_start_idx": train_start,
                "train_end_idx": t,
                "test_start_idx": test_start,
                "test_end_idx": test_start + test_bars,
                "embargo_bars": embargo_bars,
                "train_len": len(train_df),
                "test_len": len(test_df)
            }
            yield train_df, test_df, meta
            t += step_bars
            split_id += 1

    @staticmethod
    def purged_walk_forward_split(
        df: pd.DataFrame,
        n_splits: int = 5,
        embargo_pct: float = 0.01
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]]:
        """
        Splits dataset into n_splits sequential Out-Of-Sample folds with an embargo buffer
        to prevent information leakage from serially correlated returns.
        """
        n = len(df)
        embargo_bars = max(1, int(n * embargo_pct))
        fold_size = n // (n_splits + 1)
        
        splits = []
        for i in range(1, n_splits + 1):
            train_end = i * fold_size
            test_start = train_end + embargo_bars
            test_end = min(n, (i + 1) * fold_size)
            
            if test_start >= n or test_start >= test_end:
                break
                
            train_df = df.iloc[:train_end].copy()
            test_df = df.iloc[test_start:test_end].copy()
            
            meta = {
                "fold": i,
                "train_bars": len(train_df),
                "test_bars": len(test_df),
                "embargo_bars": embargo_bars,
                "train_start": str(train_df.index[0]) if isinstance(train_df.index, pd.DatetimeIndex) else 0,
                "train_end": str(train_df.index[-1]) if isinstance(train_df.index, pd.DatetimeIndex) else train_end,
                "test_start": str(test_df.index[0]) if isinstance(test_df.index, pd.DatetimeIndex) else test_start,
                "test_end": str(test_df.index[-1]) if isinstance(test_df.index, pd.DatetimeIndex) else test_end
            }
            splits.append((train_df, test_df, meta))
            
        return splits
