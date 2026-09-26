"""
Anti-Leakage Framework: Timestamp Alignment & As-Of Join Test
Verifies that multi-source alignment uses backward merge_asof, never looking into future.
"""
import pytest
import pandas as pd
import numpy as np


def test_asof_merge_prevents_future_data():
    """Verify that merging slower external data (e.g. macro/sentiment) only uses past records."""
    market_times = pd.date_range("2026-01-01 00:00:00", periods=6, freq="1h", tz="UTC")
    market_df = pd.DataFrame({
        "timestamp": market_times,
        "price": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    })

    # Macro events release at 01:30 and 03:30
    macro_times = pd.to_datetime(["2026-01-01 01:30:00", "2026-01-01 03:30:00"], utc=True)
    macro_df = pd.DataFrame({
        "timestamp": macro_times,
        "cpi_signal": [1.5, 2.0]
    })

    # merge_asof backward: at 01:00, 01:30 event is NOT known. Only becomes available at 02:00
    aligned = pd.merge_asof(market_df, macro_df, on="timestamp", direction="backward")

    # At 00:00 and 01:00, macro signal should be NaN (has not happened yet)
    assert pd.isna(aligned.iloc[0]["cpi_signal"])
    assert pd.isna(aligned.iloc[1]["cpi_signal"])
    # At 02:00, macro signal 1.5 is known
    assert aligned.iloc[2]["cpi_signal"] == 1.5
    # At 03:00, still 1.5
    assert aligned.iloc[3]["cpi_signal"] == 1.5
    # At 04:00, second event 2.0 is known
    assert aligned.iloc[4]["cpi_signal"] == 2.0
