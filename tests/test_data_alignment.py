"""
Leakage Prevention Test: Multi-Asset Alignment & Time Synchronization
======================================================================
Verifies that auxiliary data (e.g. BTC macro trend, funding rates, sentiment)
aligns causally on exact UTC timestamps with zero future forward-filling.
"""

import pytest
import numpy as np
import pandas as pd


def test_asof_merge_prevents_future_data():
    """
    Test: When joining auxiliary time-series (e.g. macro indicators),
    an as-of merge must only look backward in time, never forward.
    """
    # Asset price observations at hourly intervals
    asset_dates = pd.date_range("2024-01-01 00:00", periods=5, freq="1h", tz="UTC")
    df_asset = pd.DataFrame({"asset_price": [10.0, 10.5, 11.0, 10.8, 11.2]}, index=asset_dates)

    # Macro data published intermittently (e.g. 00:30 and 02:30)
    macro_dates = pd.to_datetime(["2024-01-01 00:30+00:00", "2024-01-01 02:30+00:00"])
    df_macro = pd.DataFrame({"macro_signal": [1.0, -1.0]}, index=macro_dates)

    # Correct merge_asof: direction='backward'
    df_merged = pd.merge_asof(
        df_asset,
        df_macro,
        left_index=True,
        right_index=True,
        direction='backward'
    )

    # At 00:00: Macro signal at 00:30 is in the FUTURE, so value at 00:00 must be NaN (not leaked!)
    assert pd.isna(df_merged.loc["2024-01-01 00:00:00+00:00", "macro_signal"])

    # At 01:00: Macro signal at 00:30 is in the PAST, so value is 1.0
    assert df_merged.loc["2024-01-01 01:00:00+00:00", "macro_signal"] == 1.0

    # At 02:00: Macro signal at 02:30 is in the FUTURE, so value must still be 1.0 from 00:30
    assert df_merged.loc["2024-01-01 02:00:00+00:00", "macro_signal"] == 1.0

    # At 03:00: Macro signal at 02:30 is now in the PAST, so value updates to -1.0
    assert df_merged.loc["2024-01-01 03:00:00+00:00", "macro_signal"] == -1.0
