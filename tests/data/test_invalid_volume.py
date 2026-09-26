import pytest
import pandas as pd
from data.validator import OHLCVValidator


def test_invalid_volume_detected():
    """Verify that negative trading volumes are flagged as errors."""
    dates = pd.date_range("2026-01-01 00:00:00", periods=5, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "timestamp": dates,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": [100.0, 50.0, -10.0, 200.0, 300.0]  # row 2 has negative volume
    })
    
    validator = OHLCVValidator(timeframe="1h")
    is_valid, report = validator.validate(df, symbol="BTCUSDT")
    
    assert not is_valid
    assert any("negative volume" in err.lower() or "volume" in err.lower() for err in report.errors)
