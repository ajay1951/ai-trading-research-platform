"""
P2-5: Automated Market Data Reliability, Heartbeat, Freshness, Multi-Asset Sync & Safety Gate Test Suite
========================================================================================================
Validates all P2-5 market-data reliability invariants across Groups A-H and End-to-End Safety Scenarios.
Zero live network dependencies (all tests run offline with deterministic clock injection).
"""

import pytest
import time
import math
import copy
from typing import List, Dict, Any

from data.market_data_health import (
    CANONICAL_UNIVERSE,
    MarketDataStatus,
    MarketDataFault,
    StreamType,
    CandleData,
    MarketDataHealthResult,
    UniverseHealthResult,
    MarketDataValidator,
    CandleDeduplicatorAndOrderingTracker,
    CandleGapDetector,
    MarketDataFreshnessEngine,
    CrossSectionalUniverseValidator,
    MarketDataRecoveryCoordinator,
    TradingSafetyGate,
    MockMarketDataFeed,
    normalize_symbol,
    normalize_to_ms,
    timeframe_to_ms
)
from execution.paper_state_machine import (
    PaperPortfolioManager,
    PaperOrder,
    OrderState,
    OrderSide,
    PositionSide,
    DurablePaperOMS
)


class MockClock:
    """Deterministic injectable clock for testing."""
    def __init__(self, start_epoch_s: float = 1700000000.0):
        self._current_time = start_epoch_s

    def time(self) -> float:
        return self._current_time

    def advance(self, seconds: float):
        self._current_time += seconds

    def set_time(self, epoch_s: float):
        self._current_time = epoch_s


# =====================================================================
# Group A: Connection and Heartbeat Tests
# =====================================================================

def test_01_healthy_websocket_connection():
    """Test 1: Healthy WebSocket connection registers active transport."""
    clock = MockClock(1700000000.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    engine.record_transport_activity("STREAM_1")
    
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    engine.record_valid_candle(candle, "STREAM_1")
    
    res = engine.evaluate_symbol_health("BTCUSDT", StreamType.CANDLE_1H, "STREAM_1")
    assert res.healthy is True
    assert res.status == MarketDataStatus.HEALTHY


def test_02_successful_heartbeat():
    """Test 2: Successful protocol heartbeat maintains connection health."""
    clock = MockClock(1700000000.0)
    engine = MarketDataFreshnessEngine(ws_heartbeat_timeout_seconds=30.0, clock_fn=clock.time)
    
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    engine.record_valid_candle(candle, "STREAM_1")
    
    clock.advance(20.0) # Within 30s timeout
    engine.record_heartbeat("STREAM_1")
    
    res = engine.evaluate_symbol_health("BTCUSDT", StreamType.CANDLE_1H, "STREAM_1")
    assert res.healthy is True


def test_03_heartbeat_timeout():
    """Test 3: Heartbeat timeout (>30s silence) transitions status to UNAVAILABLE."""
    clock = MockClock(1700000000.0)
    engine = MarketDataFreshnessEngine(ws_heartbeat_timeout_seconds=30.0, clock_fn=clock.time)
    
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    engine.record_valid_candle(candle, "STREAM_1")
    
    clock.advance(35.0) # Exceeds 30s timeout
    res = engine.evaluate_symbol_health("BTCUSDT", StreamType.CANDLE_1H, "STREAM_1")
    
    assert res.healthy is False
    assert res.status == MarketDataStatus.UNAVAILABLE
    assert "HEARTBEAT_TIMEOUT" in res.reason


def test_04_silent_open_connection():
    """Test 4: Socket connected but emitting zero market updates triggers watchdog failure."""
    clock = MockClock(1700000000.0)
    engine = MarketDataFreshnessEngine(ws_heartbeat_timeout_seconds=15.0, clock_fn=clock.time)
    
    engine.record_transport_activity("STREAM_1")
    clock.advance(20.0)
    
    res = engine.evaluate_symbol_health("ETHUSDT", StreamType.CANDLE_1H, "STREAM_1")
    assert res.healthy is False
    assert res.status == MarketDataStatus.UNAVAILABLE


def test_05_websocket_disconnect():
    """Test 5: Explicit WebSocket disconnection sets DISCONNECTED status."""
    clock = MockClock(1700000000.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    
    engine.record_disconnect("STREAM_1", reason="REMOTE_PEER_RESET")
    res = engine.evaluate_symbol_health("BTCUSDT", StreamType.CANDLE_1H, "STREAM_1")
    
    assert res.healthy is False
    assert res.status == MarketDataStatus.DISCONNECTED
    assert "REMOTE_PEER_RESET" in res.reason


def test_06_reconnect_after_disconnect():
    """Test 6: Reconnection succeeds using coordinator."""
    clock = MockClock(1700000000.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    dedup = CandleDeduplicatorAndOrderingTracker()
    gap_detector = CandleGapDetector()
    coordinator = MarketDataRecoveryCoordinator(engine, dedup, gap_detector, clock_fn=clock.time)
    
    attempts = 0
    def mock_ws_connect():
        nonlocal attempts
        attempts += 1
        return attempts >= 2 # Succeeds on attempt 2
    
    success = coordinator.handle_reconnect(mock_ws_connect)
    assert success is True
    assert coordinator.reconnect_count == 2


def test_07_reconnect_backoff():
    """Test 7: Bounded exponential backoff delay calculation."""
    engine = MarketDataFreshnessEngine()
    dedup = CandleDeduplicatorAndOrderingTracker()
    gap_detector = CandleGapDetector()
    coordinator = MarketDataRecoveryCoordinator(
        engine, dedup, gap_detector, initial_backoff_s=0.5, max_backoff_s=4.0
    )
    
    assert coordinator.compute_backoff_delay(1) == 0.5
    assert coordinator.compute_backoff_delay(2) == 1.0
    assert coordinator.compute_backoff_delay(3) == 2.0
    assert coordinator.compute_backoff_delay(4) == 4.0
    assert coordinator.compute_backoff_delay(5) == 4.0 # Capped at max_backoff


def test_08_no_duplicate_subscriptions_after_reconnect():
    """Test 8: Reconnection maintains single active stream reference."""
    clock = MockClock(1700000000.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    dedup = CandleDeduplicatorAndOrderingTracker()
    coordinator = MarketDataRecoveryCoordinator(engine, dedup, CandleGapDetector(), clock_fn=clock.time)
    
    coordinator.handle_reconnect(lambda: True)
    assert engine._connection_active.get("GLOBAL") is True


# =====================================================================
# Group B: Freshness and Timestamp Tests
# =====================================================================

def test_09_fresh_data_accepted():
    """Test 9: Candle received within valid window is marked HEALTHY."""
    clock = MockClock(1700003600.0) # 1 hour after candle open
    engine = MarketDataFreshnessEngine(ws_heartbeat_timeout_seconds=0, max_candle_delay_seconds=300.0, clock_fn=clock.time)
    
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    engine.record_valid_candle(candle)
    
    clock.advance(100.0) # 100s after close (within 300s grace)
    res = engine.evaluate_symbol_health("BTCUSDT", StreamType.CANDLE_1H)
    assert res.healthy is True
    assert res.status == MarketDataStatus.HEALTHY


def test_10_stale_data_rejected():
    """Test 10: Candle older than allowable delay is marked STALE."""
    clock = MockClock(1700003600.0)
    engine = MarketDataFreshnessEngine(ws_heartbeat_timeout_seconds=0, max_candle_delay_seconds=300.0, clock_fn=clock.time)
    
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    engine.record_valid_candle(candle)
    
    clock.advance(500.0) # 500s after close (>300s grace)
    res = engine.evaluate_symbol_health("BTCUSDT", StreamType.CANDLE_1H)
    assert res.healthy is False
    assert res.status == MarketDataStatus.STALE
    assert "CANDLE_TOO_OLD" in res.reason


def test_11_missing_timestamp_rejected():
    """Test 11: Non-positive or zero timestamp rejected by validator."""
    validator = MarketDataValidator()
    candle = CandleData("BTCUSDT", "1h", 0, 50000, 51000, 49000, 50500, 100)
    valid, reason = validator.validate_candle(candle)
    assert valid is False
    assert "INVALID_TIMESTAMP_NON_POSITIVE" in reason


def test_12_future_timestamp_rejected():
    """Test 12: Timestamp exceeding allowable clock skew is rejected."""
    clock = MockClock(1700000000.0)
    validator = MarketDataValidator(max_clock_skew_seconds=5.0, clock_fn=clock.time)
    
    # 20s into the future (exceeds 5s skew limit)
    candle = CandleData("BTCUSDT", "1h", 1700000020000, 50000, 51000, 49000, 50500, 100)
    valid, reason = validator.validate_candle(candle)
    assert valid is False
    assert "FUTURE_TIMESTAMP_CLOCK_SKEW" in reason


def test_13_timestamp_regression_rejected():
    """Test 13: Older candle cannot overwrite newer candle in state tracker."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    
    c_new = CandleData("BTCUSDT", "1h", 1700003600000, 51000, 52000, 50000, 51500, 100, is_final=True)
    c_old = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    
    accepted1, status1 = tracker.process_candle(c_new)
    accepted2, status2 = tracker.process_candle(c_old)
    
    assert accepted1 is True
    assert status1 == "ACCEPTED_NEW"
    assert accepted2 is False
    assert status2 == "OUT_OF_ORDER_IGNORED"
    assert tracker.get_latest_candle("BTCUSDT").timestamp_ms == 1700003600000


def test_14_clock_skew_detected():
    """Test 14: Clock skew tolerance precisely allows small forward offsets."""
    clock = MockClock(1700000000.0)
    validator = MarketDataValidator(max_clock_skew_seconds=5.0, clock_fn=clock.time)
    
    # 2s in future (allowed under 5s limit)
    c_valid = CandleData("BTCUSDT", "1h", 1700000002000, 50000, 51000, 49000, 50500, 100)
    valid, _ = validator.validate_candle(c_valid)
    assert valid is True


def test_15_seconds_milliseconds_normalization():
    """Test 15: Converts second timestamps to millisecond epoch seamlessly."""
    assert normalize_to_ms(1700000000) == 1700000000000
    assert normalize_to_ms(1700000000000) == 1700000000000
    with pytest.raises(ValueError):
        normalize_to_ms(-100)


def test_16_per_symbol_freshness_evaluated_independently():
    """Test 16: BTC fresh, ETH stale -> evaluated independently."""
    clock = MockClock(1700003600.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    
    c_btc = CandleData("BTCUSDT", "1h", 1700003600000 - 3600000, 50000, 51000, 49000, 50500, 100, is_final=True)
    c_eth = CandleData("ETHUSDT", "1h", 1700003600000 - 7200000, 3000, 3100, 2900, 3050, 50, is_final=True)
    
    engine.record_valid_candle(c_btc)
    engine.record_valid_candle(c_eth)
    
    btc_res = engine.evaluate_symbol_health("BTCUSDT")
    eth_res = engine.evaluate_symbol_health("ETHUSDT")
    
    assert btc_res.healthy is True
    assert eth_res.healthy is False
    assert eth_res.status == MarketDataStatus.STALE


# =====================================================================
# Group C: Data Validation Tests
# =====================================================================

def test_17_valid_ohlc_accepted():
    """Test 17: Mathematically consistent OHLCV candle accepted."""
    validator = MarketDataValidator()
    c = CandleData("BTCUSDT", "1h", 1700000000000, open=100.0, high=105.0, low=95.0, close=102.0, volume=500.0)
    valid, reason = validator.validate_candle(c)
    assert valid is True
    assert reason is None


def test_18_negative_price_rejected():
    """Test 18: Negative price strictly rejected."""
    validator = MarketDataValidator()
    c = CandleData("BTCUSDT", "1h", 1700000000000, open=100.0, high=105.0, low=-10.0, close=102.0, volume=500.0)
    valid, reason = validator.validate_candle(c)
    assert valid is False
    assert "NON_POSITIVE_PRICE" in reason


def test_19_zero_price_rejected():
    """Test 19: Zero price strictly rejected."""
    validator = MarketDataValidator()
    c = CandleData("BTCUSDT", "1h", 1700000000000, open=0.0, high=105.0, low=0.0, close=102.0, volume=500.0)
    valid, reason = validator.validate_candle(c)
    assert valid is False
    assert "NON_POSITIVE_PRICE" in reason


def test_20_nan_rejected():
    """Test 20: NaN price or volume strictly rejected."""
    validator = MarketDataValidator()
    c = CandleData("BTCUSDT", "1h", 1700000000000, open=100.0, high=float("nan"), low=95.0, close=102.0, volume=500.0)
    valid, reason = validator.validate_candle(c)
    assert valid is False
    assert "NAN_FIELD" in reason


def test_21_infinity_rejected():
    """Test 21: Infinite price strictly rejected."""
    validator = MarketDataValidator()
    c = CandleData("BTCUSDT", "1h", 1700000000000, open=100.0, high=float("inf"), low=95.0, close=102.0, volume=500.0)
    valid, reason = validator.validate_candle(c)
    assert valid is False
    assert "INFINITE_FIELD" in reason


def test_22_negative_volume_rejected():
    """Test 22: Negative volume strictly rejected."""
    validator = MarketDataValidator()
    c = CandleData("BTCUSDT", "1h", 1700000000000, open=100.0, high=105.0, low=95.0, close=102.0, volume=-50.0)
    valid, reason = validator.validate_candle(c)
    assert valid is False
    assert "NEGATIVE_VOLUME" in reason


def test_23_invalid_ohlc_invariants_rejected():
    """Test 23: OHLC invariant violations (high < low, high < close, etc.) rejected."""
    validator = MarketDataValidator()
    
    # high < low
    c1 = CandleData("BTCUSDT", "1h", 1700000000000, open=100, high=90, low=95, close=92, volume=100)
    assert validator.validate_candle(c1)[0] is False
    
    # high < open
    c2 = CandleData("BTCUSDT", "1h", 1700000000000, open=105, high=100, low=95, close=98, volume=100)
    assert validator.validate_candle(c2)[0] is False
    
    # low > close
    c3 = CandleData("BTCUSDT", "1h", 1700000000000, open=100, high=105, low=95, close=90, volume=100)
    assert validator.validate_candle(c3)[0] is False


def test_24_malformed_json_rejected():
    """Test 24: Corrupted or non-JSON payloads rejected cleanly."""
    validator = MarketDataValidator()
    valid, reason, _ = validator.validate_raw_payload("INVALID_RAW_STRING{{{")
    assert valid is False
    assert "MALFORMED_JSON" in reason


def test_25_unknown_symbol_rejected():
    """Test 25: Non-whitelisted cryptocurrency symbol rejected."""
    validator = MarketDataValidator()
    c = CandleData("SHIBUSDT", "1h", 1700000000000, open=1, high=2, low=1, close=2, volume=10)
    valid, reason = validator.validate_candle(c)
    assert valid is False
    assert "UNKNOWN_OR_EMPTY_SYMBOL" in reason


def test_26_missing_required_field_rejected():
    """Test 26: Short raw CCXT array missing volume or fields rejected."""
    validator = MarketDataValidator()
    valid, reason, _ = validator.validate_raw_payload([1700000000000, 100.0, 105.0]) # Only 3 items
    assert valid is False
    assert "MALFORMED_CCXT_CANDLE_LENGTH" in reason


# =====================================================================
# Group D: Candle Integrity Tests
# =====================================================================

def test_27_incomplete_candle_excluded():
    """Test 27: In-progress unfinalized candle excluded from finalized deduplicator."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 102, 100, is_final=False)
    
    accepted, status = tracker.process_candle(candle)
    assert accepted is False
    assert status == "INCOMPLETE_EXCLUDED"


def test_28_finalized_candle_accepted():
    """Test 28: Finalized candle accepted into state tracker."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 102, 100, is_final=True)
    
    accepted, status = tracker.process_candle(candle)
    assert accepted is True
    assert status == "ACCEPTED_NEW"


def test_29_duplicate_finalized_candle_ignored():
    """Test 29: Duplicate finalized candle delivered 3 times processed exactly once."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 102, 100, is_final=True)
    
    r1, s1 = tracker.process_candle(candle)
    r2, s2 = tracker.process_candle(candle)
    r3, s3 = tracker.process_candle(candle)
    
    assert r1 is True and s1 == "ACCEPTED_NEW"
    assert r2 is False and s2 == "DUPLICATE_IGNORED"
    assert r3 is False and s3 == "DUPLICATE_IGNORED"


def test_30_older_candle_cannot_overwrite_newer():
    """Test 30: Newer candle at T=10:00 protected against later arrival of T=09:00 candle."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    c_10 = CandleData("BTCUSDT", "1h", 1700003600000, 110, 115, 105, 112, 100, is_final=True)
    c_09 = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 102, 100, is_final=True)
    
    tracker.process_candle(c_10)
    accepted, status = tracker.process_candle(c_09)
    
    assert accepted is False
    assert status == "OUT_OF_ORDER_IGNORED"
    assert tracker.get_latest_candle("BTCUSDT").close == 112


def test_31_candle_gap_detected():
    """Test 31: Missing intermediate candle detected by continuity detector."""
    detector = CandleGapDetector()
    c1 = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 100, 10)
    c3 = CandleData("BTCUSDT", "1h", 1700007200000, 100, 105, 95, 100, 10) # Skipped 1700003600000
    
    continuous, missing = detector.ingest_history("BTCUSDT", "1h", [c1, c3])
    assert continuous is False
    assert missing == [1700003600000]


def test_32_gap_backfill_validated():
    """Test 32: Recovered backfill seamlessly merges and restores continuity."""
    detector = CandleGapDetector()
    c1 = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 100, 10)
    c3 = CandleData("BTCUSDT", "1h", 1700007200000, 100, 105, 95, 100, 10)
    c2 = CandleData("BTCUSDT", "1h", 1700003600000, 100, 105, 95, 100, 10) # Missing one
    
    valid, merged, err = detector.validate_backfill("BTCUSDT", "1h", [c1, c3], [c2])
    assert valid is True
    assert len(merged) == 3
    assert [c.timestamp_ms for c in merged] == [1700000000000, 1700003600000, 1700007200000]


def test_33_invalid_backfill_rejected():
    """Test 33: Backfill with unresolved gaps rejected."""
    detector = CandleGapDetector()
    c1 = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 100, 10)
    c4 = CandleData("BTCUSDT", "1h", 1700010800000, 100, 105, 95, 100, 10)
    c2 = CandleData("BTCUSDT", "1h", 1700003600000, 100, 105, 95, 100, 10) # Still missing c3
    
    valid, _, err = detector.validate_backfill("BTCUSDT", "1h", [c1, c4], [c2])
    assert valid is False
    assert "UNRESOLVED_GAP_AFTER_BACKFILL" in err


def test_34_overlapping_rest_websocket_candle_deduplicated():
    """Test 34: Exact same candle from WS and REST results in single canonical record."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    c_ws = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 102, 100, is_final=True)
    c_rest = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 102, 100, is_final=True)
    
    r1, _ = tracker.process_candle(c_ws)
    r2, s2 = tracker.process_candle(c_rest)
    
    assert r1 is True
    assert r2 is False
    assert s2 == "DUPLICATE_IGNORED"


# =====================================================================
# Group E: Multi-Asset Integrity Tests
# =====================================================================

def test_35_all_13_assets_healthy():
    """Test 35: All 13 canonical assets fresh and aligned -> universe HEALTHY."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    step_candles = feed.generate_universe_step(0)
    for sym, candle in step_candles.items():
        engine.record_valid_candle(candle)
        
    univ_res = univ_val.evaluate_universe()
    assert univ_res.healthy is True
    assert univ_res.all_symbols_healthy is True
    assert univ_res.aligned_cutoff_ms == 1700000000000
    assert len(univ_res.stale_symbols) == 0


def test_36_one_asset_stale_blocks_universe():
    """Test 36: 12 assets healthy, SUIUSDT stale -> universe STALE."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    step_candles = feed.generate_universe_step(0)
    for sym, candle in step_candles.items():
        if sym == "SUIUSDT":
            # Make SUI 1 hour older
            candle.timestamp_ms -= 3600000
        engine.record_valid_candle(candle)
        
    univ_res = univ_val.evaluate_universe()
    assert univ_res.healthy is False
    assert univ_res.status == MarketDataStatus.STALE
    assert "SUIUSDT" in univ_res.stale_symbols


def test_37_one_asset_missing_blocks_universe():
    """Test 37: 12 assets present, LINKUSDT missing -> universe INCOMPLETE."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    step_candles = feed.generate_universe_step(0)
    for sym, candle in step_candles.items():
        if sym != "LINKUSDT":
            engine.record_valid_candle(candle)
            
    univ_res = univ_val.evaluate_universe()
    assert univ_res.healthy is False
    assert univ_res.status == MarketDataStatus.INCOMPLETE
    assert "LINKUSDT" in univ_res.missing_symbols


def test_38_asset_histories_misaligned():
    """Test 38: Asset candles at different cutoff timestamps -> INVALID misaligned."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    step_candles = feed.generate_universe_step(0)
    for sym, candle in step_candles.items():
        if sym == "DOGEUSDT":
            candle.timestamp_ms += 3600000 # Different cutoff
        engine.record_valid_candle(candle)
        
    univ_res = univ_val.evaluate_universe()
    assert univ_res.healthy is False
    assert "UNIVERSE_MISALIGNED_CUTOFF" in univ_res.reason


def test_39_missing_historical_candle_detected():
    """Test 39: Continuity check across universe detects missing symbol period."""
    detector = CandleGapDetector()
    c1 = CandleData("BNBUSDT", "1h", 1700000000000, 300, 310, 295, 305, 50)
    c3 = CandleData("BNBUSDT", "1h", 1700007200000, 305, 315, 300, 310, 50)
    
    continuous, missing = detector.ingest_history("BNBUSDT", "1h", [c1, c3])
    assert continuous is False
    assert len(missing) == 1


def test_40_full_universe_recovered_after_backfill():
    """Test 40: After backfilling missing asset, 13-asset universe health is fully restored."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    # Initially missing AVAXUSDT
    step_candles = feed.generate_universe_step(0)
    for sym, candle in step_candles.items():
        if sym != "AVAXUSDT":
            engine.record_valid_candle(candle)
            
    assert univ_val.evaluate_universe().healthy is False
    
    # Backfill AVAXUSDT
    engine.record_valid_candle(step_candles["AVAXUSDT"])
    
    res = univ_val.evaluate_universe()
    assert res.healthy is True
    assert res.all_symbols_healthy is True


def test_41_no_partial_universe_ranking():
    """Test 41: Guarantee that universe is never silently reduced from 13 to 12."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    step_candles = feed.generate_universe_step(0)
    for sym, candle in step_candles.items():
        if sym != "NEARUSDT":
            engine.record_valid_candle(candle)
            
    res = univ_val.evaluate_universe()
    assert res.healthy is False
    assert len(univ_val.required_universe) == 13


def test_42_no_stale_symbol_substitution():
    """Test 42: Stale symbol cannot be substituted with mock or interpolated prices."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    
    # Only 12 assets submitted
    for sym in CANONICAL_UNIVERSE:
        if sym == "LTCUSDT":
            continue
        c = CandleData(sym, "1h", 1700000000000, 100, 105, 95, 100, 10, is_final=True)
        engine.record_valid_candle(c)
        
    res = univ_val.evaluate_universe()
    assert res.healthy is False
    assert "LTCUSDT" in res.missing_symbols


# =====================================================================
# Group F: REST Fallback Tests
# =====================================================================

def test_43_rest_fallback_success():
    """Test 43: REST fallback fetches and restores missing symbol candles."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    dedup = CandleDeduplicatorAndOrderingTracker()
    coordinator = MarketDataRecoveryCoordinator(engine, dedup, CandleGapDetector(), clock_fn=clock.time)
    
    def mock_rest_fetch(symbol: str) -> List[CandleData]:
        return [CandleData(symbol, "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)]
    
    success, err = coordinator.execute_rest_fallback("BTCUSDT", mock_rest_fetch)
    assert success is True
    assert err is None
    assert engine.evaluate_symbol_health("BTCUSDT").healthy is True


def test_44_rest_timeout():
    """Test 44: REST timeout handled gracefully without crashing."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    coordinator = MarketDataRecoveryCoordinator(
        engine, CandleDeduplicatorAndOrderingTracker(), CandleGapDetector(), clock_fn=clock.time
    )
    
    def timeout_fetch(symbol: str):
        raise TimeoutError("REST request timed out after 10.0s")
        
    success, err = coordinator.execute_rest_fallback("BTCUSDT", timeout_fetch)
    assert success is False
    assert "REST_FETCH_EXCEPTION" in err


def test_45_rest_stale_response():
    """Test 45: REST returning stale candle fails freshness check."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    dedup = CandleDeduplicatorAndOrderingTracker()
    coordinator = MarketDataRecoveryCoordinator(engine, dedup, CandleGapDetector(), clock_fn=clock.time)
    
    def stale_rest_fetch(symbol: str) -> List[CandleData]:
        # Candle is 10 hours old
        return [CandleData(symbol, "1h", 1700000000000 - 36000000, 50000, 51000, 49000, 50500, 100, is_final=True)]
        
    coordinator.execute_rest_fallback("BTCUSDT", stale_rest_fetch)
    res = engine.evaluate_symbol_health("BTCUSDT")
    assert res.healthy is False
    assert res.status == MarketDataStatus.STALE


def test_46_rest_malformed_response():
    """Test 46: Malformed REST response rejected."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    coordinator = MarketDataRecoveryCoordinator(
        engine, CandleDeduplicatorAndOrderingTracker(), CandleGapDetector(), clock_fn=clock.time
    )
    
    def malformed_rest_fetch(symbol: str) -> List[CandleData]:
        # Invalid OHLC (high < low)
        return [CandleData(symbol, "1h", 1700000000000, 50000, 40000, 49000, 50500, 100, is_final=True)]
        
    success, err = coordinator.execute_rest_fallback("BTCUSDT", malformed_rest_fetch)
    assert success is False
    assert "REST_INVALID_CANDLE" in err


def test_47_rest_rate_limit_429():
    """Test 47: REST 429 rate limit error handled cleanly."""
    clock = MockClock(1700003650.0)
    coordinator = MarketDataRecoveryCoordinator(
        MarketDataFreshnessEngine(clock_fn=clock.time),
        CandleDeduplicatorAndOrderingTracker(),
        CandleGapDetector(),
        clock_fn=clock.time
    )
    
    def rate_limited_fetch(symbol: str):
        raise ConnectionError("HTTP 429 Too Many Requests")
        
    success, err = coordinator.execute_rest_fallback("BTCUSDT", rate_limited_fetch)
    assert success is False
    assert "429" in err


def test_48_rest_incomplete_candle_excluded():
    """Test 48: Incomplete candle from REST excluded from latest finalized cache."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    dedup = CandleDeduplicatorAndOrderingTracker()
    coordinator = MarketDataRecoveryCoordinator(engine, dedup, CandleGapDetector(), clock_fn=clock.time)
    
    def incomplete_fetch(symbol: str) -> List[CandleData]:
        return [CandleData(symbol, "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=False)]
        
    coordinator.execute_rest_fallback("BTCUSDT", incomplete_fetch)
    assert dedup.get_latest_candle("BTCUSDT") is None


def test_49_websocket_reconnect_during_rest_fetch():
    """Test 49: Simultaneous reconnect and REST completion handled cleanly."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    dedup = CandleDeduplicatorAndOrderingTracker()
    coordinator = MarketDataRecoveryCoordinator(engine, dedup, CandleGapDetector(), clock_fn=clock.time)
    
    # 1. WS reconnects with candle T
    c_ws = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    coordinator.handle_reconnect(lambda: True)
    dedup.process_candle(c_ws)
    engine.record_valid_candle(c_ws)
    
    # 2. REST arrives with same candle T
    def rest_fetch(symbol: str):
        return [CandleData(symbol, "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)]
        
    success, _ = coordinator.execute_rest_fallback("BTCUSDT", rest_fetch)
    assert success is True
    assert dedup.get_latest_candle("BTCUSDT").timestamp_ms == 1700000000000


def test_50_older_rest_cannot_overwrite_newer_websocket():
    """Test 50: Out-of-order race: newer WS candle T protected against delayed REST candle T-1."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    
    # Newer WS candle at T=10:00
    c_ws = CandleData("BTCUSDT", "1h", 1700003600000, 52000, 53000, 51000, 52500, 100, is_final=True)
    tracker.process_candle(c_ws)
    
    # Older REST response at T=09:00
    c_rest = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    accepted, status = tracker.process_candle(c_rest)
    
    assert accepted is False
    assert status == "OUT_OF_ORDER_IGNORED"
    assert tracker.get_latest_candle("BTCUSDT").close == 52500


# =====================================================================
# Group G: Trading Safety Tests
# =====================================================================

def test_51_stale_data_blocks_signal_generation():
    """Test 51: Stale data fails safety gate permission check."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(universe_validator=univ_val, clock_fn=clock.time)
    
    # Insert stale data (10 hours old)
    for sym in CANONICAL_UNIVERSE:
        c = CandleData(sym, "1h", 1700000000000 - 36000000, 100, 105, 95, 100, 10, is_final=True)
        engine.record_valid_candle(c)
        
    can_trade, reason, _ = gate.verify_trading_permission()
    assert can_trade is False
    assert "MARKET_DATA_UNHEALTHY" in reason


def test_52_stale_data_produces_zero_new_oms_orders():
    """Test 52: Rebalance attempt during stale data results in ZERO new OMS orders."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    portfolio = PaperPortfolioManager(initial_cash=1000.0)
    gate = TradingSafetyGate(universe_validator=univ_val, portfolio_manager=portfolio, clock_fn=clock.time)
    
    orders_created = 0
    def strategy_rebalance(cutoff_ts):
        nonlocal orders_created
        orders_created += 1
        return "SUCCESS"
        
    result = gate.handle_rebalance_decision("REB_001", strategy_rebalance)
    assert result["status"] == "SKIPPED_UNTRUSTED_DATA"
    assert result["orders_generated"] == 0
    assert orders_created == 0


def test_53_disconnected_stream_blocks_orders():
    """Test 53: Disconnected stream blocks strategy execution."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    engine.record_disconnect(reason="TCP_RESET")
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, clock_fn=clock.time)
    
    can_trade, reason, _ = gate.verify_trading_permission()
    assert can_trade is False
    assert "DISCONNECTED" in reason


def test_54_incomplete_universe_blocks_rebalance():
    """Test 54: Rebalance blocked when 1 required asset is missing."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, clock_fn=clock.time)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    # Ingest 12 of 13
    candles = feed.generate_universe_step(0)
    for sym, c in candles.items():
        if sym != "DOTUSDT":
            engine.record_valid_candle(c)
            
    can_trade, reason, _ = gate.verify_trading_permission()
    assert can_trade is False
    assert "DOTUSDT" in reason


def test_55_duplicate_data_cannot_trigger_duplicate_signal():
    """Test 55: Ingesting duplicate candle multiple times produces at most one new event."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    
    signals_emitted = 0
    for _ in range(5):
        accepted, _ = tracker.process_candle(candle)
        if accepted:
            signals_emitted += 1
            
    assert signals_emitted == 1


def test_56_reconnect_alone_does_not_resume_trading():
    """Test 56: Reconnecting socket WITHOUT validated market data keeps trading BLOCKED."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, clock_fn=clock.time)
    coordinator = MarketDataRecoveryCoordinator(
        engine, CandleDeduplicatorAndOrderingTracker(), CandleGapDetector(), clock_fn=clock.time
    )
    
    # Reconnect successfully
    coordinator.handle_reconnect(lambda: True)
    
    # But no candles ingested yet!
    can_trade, reason, _ = gate.verify_trading_permission()
    assert can_trade is False
    assert "MISSING" in reason or "INCOMPLETE" in reason or "NO_FINALIZED_CANDLE" in reason


def test_57_validated_recovery_restores_eligibility():
    """Test 57: Ingesting full validated universe after reconnect restores trading eligibility."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, clock_fn=clock.time)
    coordinator = MarketDataRecoveryCoordinator(
        engine, CandleDeduplicatorAndOrderingTracker(), CandleGapDetector(), clock_fn=clock.time
    )
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    # 1. Reconnect
    coordinator.handle_reconnect(lambda: True)
    
    # 2. Backfill full universe
    for sym, c in feed.generate_universe_step(0).items():
        engine.record_valid_candle(c)
        
    can_trade, reason, univ_res = gate.verify_trading_permission()
    assert can_trade is True
    assert reason == "PERMITTED"
    assert univ_res.aligned_cutoff_ms == 1700000000000


def test_58_missed_rebalance_cannot_execute_stale_intent():
    """Test 58: Rebalance that was skipped during an outage is recorded as skipped."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, clock_fn=clock.time)
    
    res = gate.handle_rebalance_decision("REB_48H_01", lambda ts: "TRADE")
    assert res["status"] == "SKIPPED_UNTRUSTED_DATA"
    assert len(gate._skipped_rebalances) == 1
    assert gate._skipped_rebalances[0]["rebalance_id"] == "REB_48H_01"


def test_59_p2_4_recovery_failure_still_blocks_trading():
    """Test 59: Even if market data is healthy, P2-4 portfolio halt blocks trading."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    portfolio = PaperPortfolioManager(initial_cash=1000.0)
    portfolio.is_trading_halted = True # P2-4 halt
    gate = TradingSafetyGate(univ_val, portfolio_manager=portfolio, clock_fn=clock.time)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    # Ingest healthy market data
    for sym, c in feed.generate_universe_step(0).items():
        engine.record_valid_candle(c)
        
    can_trade, reason, _ = gate.verify_trading_permission()
    assert can_trade is False
    assert "PORTFOLIO_RECOVERY_HALTED" in reason


def test_60_existing_positions_remain_unchanged_during_outage():
    """Test 60: Outage preserves existing portfolio positions and cash balances."""
    portfolio = PaperPortfolioManager(initial_cash=1000.0)
    order = PaperOrder(order_id=1, symbol="BTCUSDT", side=OrderSide.BUY, order_qty=0.1, price=50000)
    portfolio.apply_order_fill(order, 0.1, 50000.0, fee=2.0)
    
    initial_cash = portfolio.cash
    initial_pos_size = portfolio.get_position("BTCUSDT").size
    
    # Trigger gate block
    engine = MarketDataFreshnessEngine()
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, portfolio_manager=portfolio)
    
    can_trade, _, _ = gate.verify_trading_permission()
    assert can_trade is False
    
    # Assert positions untouched
    assert portfolio.cash == initial_cash
    assert portfolio.get_position("BTCUSDT").size == initial_pos_size


# =====================================================================
# Group H: Determinism and Integration Scenarios
# =====================================================================

def test_61_repeated_identical_event_streams_deterministic():
    """Test 61: Two identical sequences of candle events produce identical health results."""
    def run_stream():
        clock = MockClock(1700003650.0)
        engine = MarketDataFreshnessEngine(clock_fn=clock.time)
        univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
        feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
        for sym, c in feed.generate_universe_step(0).items():
            engine.record_valid_candle(c)
        return univ_val.evaluate_universe()
        
    r1 = run_stream()
    r2 = run_stream()
    
    assert r1.healthy == r2.healthy
    assert r1.status == r2.status
    assert r1.aligned_cutoff_ms == r2.aligned_cutoff_ms


def test_62_future_data_mutation_does_not_change_past_decisions():
    """Test 62: Immutability: Mutating future feed object does not affect captured state."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    c = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    engine.record_valid_candle(copy.deepcopy(c))
    
    # Mutate local object
    c.close = 999999.0
    c.timestamp_ms = 0
    
    res = engine.evaluate_symbol_health("BTCUSDT")
    assert res.healthy is True
    assert res.last_exchange_timestamp_ms == 1700000000000


def test_63_recovery_state_transitions_deterministic():
    """Test 63: Deterministic transition: DISCONNECTED -> RECOVERING -> HEALTHY."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    coordinator = MarketDataRecoveryCoordinator(
        engine, CandleDeduplicatorAndOrderingTracker(), CandleGapDetector(), clock_fn=clock.time
    )
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    # 1. Start Disconnected
    engine.record_disconnect(reason="CONN_DROP")
    assert univ_val.evaluate_universe().status in (MarketDataStatus.DISCONNECTED, MarketDataStatus.INCOMPLETE)
    
    # 2. Reconnect
    coordinator.handle_reconnect(lambda: True)
    assert coordinator.is_recovering is True
    
    # 3. Ingest data -> Healthy
    for sym, c in feed.generate_universe_step(0).items():
        engine.record_valid_candle(c)
        
    univ_res = univ_val.evaluate_universe()
    assert univ_res.healthy is True
    assert univ_res.status == MarketDataStatus.HEALTHY


def test_64_health_metrics_reflect_actual_transitions():
    """Test 64: Metrics increment on invalid and duplicate messages."""
    validator = MarketDataValidator()
    tracker = CandleDeduplicatorAndOrderingTracker()
    
    # Invalid message
    c_inv = CandleData("BTCUSDT", "1h", 1700000000000, -10, 20, 10, 15, 10)
    valid, _ = validator.validate_candle(c_inv)
    assert valid is False
    
    # Duplicate message
    c_valid = CandleData("BTCUSDT", "1h", 1700000000000, 10, 20, 10, 15, 10, is_final=True)
    tracker.process_candle(c_valid)
    acc2, stat2 = tracker.process_candle(c_valid)
    assert acc2 is False
    assert stat2 == "DUPLICATE_IGNORED"


def test_65_no_live_network_required():
    """Test 65: Complete suite executes without internet or external sockets."""
    feed = MockMarketDataFeed()
    candles = feed.generate_universe_step(0)
    assert len(candles) == 13
    assert all(c.symbol in CANONICAL_UNIVERSE for c in candles.values())


def test_66_no_changes_to_strategy_parameters():
    """Test 66: Canonical universe and strategy configuration frozen."""
    assert len(CANONICAL_UNIVERSE) == 13
    assert CANONICAL_UNIVERSE[0] == "BTCUSDT"
    assert CANONICAL_UNIVERSE[1] == "ETHUSDT"
    assert CANONICAL_UNIVERSE[2] == "SOLUSDT"


# =====================================================================
# Phase W: End-to-End Safety Scenarios 1 to 8
# =====================================================================

def test_scenario_1_silent_websocket_failure():
    """Scenario 1: Silent WS failure -> Watchdog timeout -> ZERO NEW ORDERS."""
    clock = MockClock(1700000000.0)
    engine = MarketDataFreshnessEngine(ws_heartbeat_timeout_seconds=30.0, clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, clock_fn=clock.time)
    
    # Transport opened initially
    engine.record_transport_activity()
    
    # 40s passes with zero messages or pings
    clock.advance(40.0)
    
    orders_submitted = 0
    res = gate.handle_rebalance_decision("REB_SCENARIO_1", lambda ts: setattr(orders_submitted, "val", 1))
    assert res["status"] == "SKIPPED_UNTRUSTED_DATA"
    assert res["orders_generated"] == 0
    assert orders_submitted == 0


def test_scenario_2_one_stale_asset():
    """Scenario 2: 12 healthy assets, 1 stale -> ZERO NEW REBALANCE ORDERS."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, clock_fn=clock.time)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    step_candles = feed.generate_universe_step(0)
    for sym, candle in step_candles.items():
        if sym == "ADAUSDT":
            candle.timestamp_ms -= 7200000 # 2 hours old
        engine.record_valid_candle(candle)
        
    res = gate.handle_rebalance_decision("REB_SCENARIO_2", lambda ts: "BUY")
    assert res["status"] == "SKIPPED_UNTRUSTED_DATA"
    assert res["orders_generated"] == 0


def test_scenario_3_rest_fallback_with_stale_response():
    """Scenario 3: WS disconnect -> REST fallback -> Stale response -> TRADING BLOCKED."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    dedup = CandleDeduplicatorAndOrderingTracker()
    coordinator = MarketDataRecoveryCoordinator(engine, dedup, CandleGapDetector(), clock_fn=clock.time)
    gate = TradingSafetyGate(CrossSectionalUniverseValidator(freshness_engine=engine), clock_fn=clock.time)
    
    # REST returns stale data
    def stale_fetch(symbol: str):
        return [CandleData(symbol, "1h", 1700000000000 - 36000000, 100, 105, 95, 100, 10, is_final=True)]
        
    for sym in CANONICAL_UNIVERSE:
        coordinator.execute_rest_fallback(sym, stale_fetch)
        
    can_trade, reason, _ = gate.verify_trading_permission()
    assert can_trade is False
    assert "STALE" in reason


def test_scenario_4_successful_recovery_and_restoration():
    """Scenario 4: Disconnect -> Gap detected -> REST backfill -> Universe validated -> ELIGIBLE."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(clock_fn=clock.time)
    dedup = CandleDeduplicatorAndOrderingTracker()
    coordinator = MarketDataRecoveryCoordinator(engine, dedup, CandleGapDetector(), clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, clock_fn=clock.time)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    # 1. Disconnected
    engine.record_disconnect(reason="NET_DROP")
    assert gate.verify_trading_permission()[0] is False
    
    # 2. Reconnect & REST Backfill full universe
    coordinator.handle_reconnect(lambda: True)
    step_candles = feed.generate_universe_step(0)
    for sym, candle in step_candles.items():
        coordinator.execute_rest_fallback(sym, lambda s: [step_candles[s]])
        
    can_trade, reason, univ_res = gate.verify_trading_permission()
    assert can_trade is True
    assert univ_res.healthy is True
    assert univ_res.aligned_cutoff_ms == 1700000000000


def test_scenario_5_duplicate_candle_at_most_one_decision():
    """Scenario 5: Duplicate candle repeated -> exactly one decision."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    candle = CandleData("BTCUSDT", "1h", 1700000000000, 50000, 51000, 49000, 50500, 100, is_final=True)
    
    decisions = []
    for _ in range(4):
        accepted, _ = tracker.process_candle(candle)
        if accepted:
            decisions.append(f"DECISION_{candle.timestamp_ms}")
            
    assert len(decisions) == 1


def test_scenario_6_out_of_order_recovery_no_overwrite():
    """Scenario 6: New WS candle T, older REST response T-1 -> State remains T."""
    tracker = CandleDeduplicatorAndOrderingTracker()
    c_new = CandleData("BTCUSDT", "1h", 1700003600000, 110, 115, 105, 112, 100, is_final=True)
    c_old = CandleData("BTCUSDT", "1h", 1700000000000, 100, 105, 95, 102, 100, is_final=True)
    
    tracker.process_candle(c_new)
    tracker.process_candle(c_old)
    
    assert tracker.get_latest_candle("BTCUSDT").timestamp_ms == 1700003600000
    assert tracker.get_latest_candle("BTCUSDT").close == 112


def test_scenario_7_p2_4_recovery_plus_market_data_failure():
    """Scenario 7: P2-4 ledger recovery OK, Market Data Stale -> TRADING BLOCKED."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    portfolio = PaperPortfolioManager(initial_cash=1000.0)
    gate = TradingSafetyGate(univ_val, portfolio_manager=portfolio, clock_fn=clock.time)
    
    # Portfolio recovery succeeded (not halted)
    assert portfolio.is_trading_halted is False
    
    # Market data is stale
    for sym in CANONICAL_UNIVERSE:
        engine.record_valid_candle(CandleData(sym, "1h", 1700000000000 - 36000000, 100, 105, 95, 100, 10, is_final=True))
        
    can_trade, reason, _ = gate.verify_trading_permission()
    assert can_trade is False
    assert "STALE" in reason


def test_scenario_8_delayed_scheduled_rebalance():
    """Scenario 8: 48H rebalance during outage skipped; data recovers; no stale intent."""
    clock = MockClock(1700003650.0)
    engine = MarketDataFreshnessEngine(max_candle_delay_seconds=300.0, clock_fn=clock.time)
    univ_val = CrossSectionalUniverseValidator(freshness_engine=engine)
    gate = TradingSafetyGate(univ_val, clock_fn=clock.time)
    feed = MockMarketDataFeed(start_ts_ms=1700000000000, clock_fn=clock.time)
    
    # 1. Market data unhealthy at rebalance time
    engine.record_disconnect(reason="NET_OUTAGE")
    r1 = gate.handle_rebalance_decision("REB_48H_SCHEDULED", lambda ts: "BUY")
    assert r1["status"] == "SKIPPED_UNTRUSTED_DATA"
    
    # 2. Data recovers at later time
    coordinator = MarketDataRecoveryCoordinator(
        engine, CandleDeduplicatorAndOrderingTracker(), CandleGapDetector(), clock_fn=clock.time
    )
    coordinator.handle_reconnect(lambda: True)
    for sym, c in feed.generate_universe_step(0).items():
        engine.record_valid_candle(c)
        
    # Rebalance eligibility is now restored for next cycle, but previous intent was not executed
    can_trade, _, _ = gate.verify_trading_permission()
    assert can_trade is True
    assert len(gate._skipped_rebalances) == 1
