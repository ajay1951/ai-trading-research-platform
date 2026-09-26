import pytest
import pandas as pd
import numpy as np
from data.validator import OHLCVValidator


def test_missing_candles_detected():
    """Verify that OHLCVValidator detects missing hourly candles."""
    dates = pd.date_range("2026-01-01 00:00:00", periods=20, freq="1h", tz="UTC")
    # Drop 2 candles in the middle (e.g. index 5 and 6)
    dates_with_gap = dates.delete([5, 6])
    
    df = pd.DataFrame({
        "timestamp": dates_with_gap,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 1000.0
    })
    
    validator = OHLCVValidator(timeframe="1h", allow_gaps=False)
    is_valid, report = validator.validate(df, symbol="BTCUSDT")
    
    assert not is_valid
    assert any("gap" in err.lower() or "missing" in err.lower() for err in report.errors)
    assert report.metrics.get("detected_gaps_count", 0) >= 1
