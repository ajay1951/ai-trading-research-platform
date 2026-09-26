import pytest
import pandas as pd
from data.validator import OHLCVValidator


def test_timestamp_alignment_valid():
    """Verify that regularly spaced, aligned timestamps pass validation."""
    dates = pd.date_range("2026-01-01 00:00:00", periods=24, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "timestamp": dates,
        "open": [100.0 + i for i in range(24)],
        "high": [105.0 + i for i in range(24)],
        "low": [98.0 + i for i in range(24)],
        "close": [102.0 + i for i in range(24)],
        "volume": [500.0 + i * 10 for i in range(24)]
    })
    
    validator = OHLCVValidator(timeframe="1h")
    is_valid, report = validator.validate(df, symbol="BTCUSDT")
    
    assert is_valid
    assert len(report.errors) == 0
    assert report.total_rows == 24
