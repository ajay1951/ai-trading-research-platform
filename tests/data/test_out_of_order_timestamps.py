import pytest
import pandas as pd
from data.validator import OHLCVValidator


def test_out_of_order_timestamps_detected():
    """Verify that non-monotonic timestamps are flagged."""
    dates = pd.date_range("2026-01-01 00:00:00", periods=10, freq="1h", tz="UTC").tolist()
    # Swap two elements to make timestamps non-monotonic
    dates[4], dates[5] = dates[5], dates[4]
    
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
    assert any("monotonic" in err.lower() or "order" in err.lower() for err in report.errors)
