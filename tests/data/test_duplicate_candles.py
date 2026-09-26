import pytest
import pandas as pd
from data.validator import OHLCVValidator


def test_duplicate_candles_detected():
    """Verify that duplicate timestamps are caught and flagged as errors."""
    dates = list(pd.date_range("2026-01-01 00:00:00", periods=10, freq="1h", tz="UTC"))
    # Duplicate index 3
    dates.insert(3, dates[3])
    
    df = pd.DataFrame({
        "timestamp": dates,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 1000.0
    })
    
    validator = OHLCVValidator(timeframe="1h")
    is_valid, report = validator.validate(df, symbol="BTCUSDT")
    
    assert not is_valid
    assert any("duplicate" in err.lower() for err in report.errors)
    assert report.metrics.get("duplicate_timestamps", 0) >= 1
