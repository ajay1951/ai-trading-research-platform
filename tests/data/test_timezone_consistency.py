import pytest
import pandas as pd
from data.validator import OHLCVValidator


def test_timezone_standardization():
    """Verify that timestamp columns are parsed into standardized UTC."""
    dates_naive = pd.date_range("2026-01-01 00:00:00", periods=5, freq="1h")
    df = pd.DataFrame({
        "timestamp": dates_naive.astype(str),
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 1000.0
    })
    
    validator = OHLCVValidator(timeframe="1h")
    is_valid, report = validator.validate(df, symbol="BTCUSDT")
    
    assert is_valid
    assert "UTC" in report.start_time or "Z" in report.start_time or "+00:00" in report.start_time
