import pytest
import pandas as pd
from data.validator import OHLCVValidator


def test_invalid_prices_detected():
    """Verify that price anomalies (High < Low, Low <= 0, Open outside range) are rejected."""
    dates = pd.date_range("2026-01-01 00:00:00", periods=4, freq="1h", tz="UTC")
    
    # Row 1: Low > High
    # Row 2: Negative price
    # Row 3: Close > High
    df = pd.DataFrame({
        "timestamp": dates,
        "open": [100.0, 100.0, 100.0, 100.0],
        "high": [90.0, 105.0, 105.0, 105.0],    # row 0 has high < low
        "low": [95.0, -10.0, 95.0, 95.0],      # row 1 has negative low
        "close": [92.0, 100.0, 120.0, 102.0],   # row 2 has close > high
        "volume": [1000.0, 1000.0, 1000.0, 1000.0]
    })
    
    validator = OHLCVValidator(timeframe="1h")
    is_valid, report = validator.validate(df, symbol="BTCUSDT")
    
    assert not is_valid
    assert len(report.errors) > 0
    assert any("price" in err.lower() or "high" in err.lower() for err in report.errors)
