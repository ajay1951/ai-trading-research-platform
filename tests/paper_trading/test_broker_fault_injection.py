"""
P2-6: Automated Broker/API Fault Injection, Execution Uncertainty & Safe Recovery Test Suite
============================================================================================
Validates all P2-6 broker fault injection, error classification, uncertainty handling,
status recovery, cancel/fill races, and accounting invariants across Groups 1-63.
Zero live network dependencies (all tests run offline with deterministic clock/broker injection).
"""

import os
import uuid
import shutil
import pytest
import sqlite3
import tempfile
import threading
from typing import Dict, Any, List

from execution.paper_state_machine import (
    OrderState,
    OrderEventType,
    OrderSide,
    PositionSide,
    OrderRejectionReason,
    PaperOrder,
    PaperStateMachine,
    PaperPortfolioManager,
    DurablePaperOMS,
    InvalidOrderTransition,
    OrderInvariantViolation,
    OverfillRejected,
    IdempotencyConflict,
    generate_client_order_id
)
from execution.broker_adapter import (
    BrokerFault,
    BrokerErrorCategory,
    BrokerStatusResult,
    BrokerOrderRecord,
    FakeBroker,
    BrokerAdapter
)
from data.market_data_health import (
    CANONICAL_UNIVERSE,
    MarketDataFreshnessEngine,
    CrossSectionalUniverseValidator,
    TradingSafetyGate
)


@pytest.fixture
def test_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def broker_setup(test_dir):
    db_path = os.path.join(test_dir, "test_broker_oms.db")
    oms = DurablePaperOMS(db_path=db_path)
    portfolio = PaperPortfolioManager(initial_cash=1000.0)
    fake_broker = FakeBroker()
    adapter = BrokerAdapter(oms=oms, portfolio_manager=portfolio, fake_broker=fake_broker)
    yield oms, portfolio, fake_broker, adapter
    oms.close()


# =====================================================================
# Group 1: Request Transmission Tests
# =====================================================================

def test_01_successful_submission(broker_setup):
    """Test 1: Normal successful submission transitions order to ACKNOWLEDGED/FILLED."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order)
    assert err is None
    assert order.state == OrderState.FILLED
    assert order.filled_qty == 0.1
    assert portfolio.get_position("BTCUSDT").size == 0.1


def test_02_failure_before_send(broker_setup):
    """Test 2: Pre-send connection failure retries safely without creating broker order."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.CONNECTION_ERROR_BEFORE_SEND)
    assert cat == BrokerErrorCategory.RECOVERY_FAILED
    assert len(broker.orders) == 0
    assert portfolio.get_position("BTCUSDT").size == 0.0


def test_03_timeout_before_send(broker_setup):
    """Test 3: Pre-send timeout categorized as PRE_SEND_FAILURE."""
    oms, portfolio, broker, adapter = broker_setup
    cat = adapter.classify_error(TimeoutError("Pre-send socket timeout"), request_sent=False)
    assert cat == BrokerErrorCategory.PRE_SEND_FAILURE


def test_04_connection_error_before_send(broker_setup):
    """Test 4: Pre-send DNS error categorized as PRE_SEND_FAILURE."""
    oms, portfolio, broker, adapter = broker_setup
    cat = adapter.classify_error(ConnectionError("DNS failure"), request_sent=False)
    assert cat == BrokerErrorCategory.PRE_SEND_FAILURE


def test_05_timeout_after_send_enters_unknown(broker_setup):
    """Test 5: Post-send timeout transitions order to UNKNOWN (not rejected!)."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN
    assert order.state == OrderState.UNKNOWN
    assert portfolio.get_position("BTCUSDT").size == 0.0


def test_06_connection_reset_after_send_enters_unknown(broker_setup):
    """Test 6: Post-send TCP reset transitions order to UNKNOWN."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="ETHUSDT", side="BUY", total_qty=1.0, price=3000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.CONNECTION_RESET_AFTER_SEND)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN
    assert order.state == OrderState.UNKNOWN


def test_07_lost_response_after_send_enters_unknown(broker_setup):
    """Test 7: Lost response packet transitions order to UNKNOWN."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="SOLUSDT", side="BUY", total_qty=5.0, price=100.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.LOST_RESPONSE_AFTER_SEND)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN
    assert order.state == OrderState.UNKNOWN


# =====================================================================
# Group 2: HTTP & Payload Error Tests
# =====================================================================

def test_08_http_400_deterministic_rejection(broker_setup):
    """Test 8: HTTP 400 Bad Request transitions order to REJECTED."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.HTTP_400_INVALID_PARAMS)
    assert cat == BrokerErrorCategory.DETERMINISTIC_REJECTION
    assert order.state == OrderState.REJECTED
    assert portfolio.get_position("BTCUSDT").size == 0.0


def test_09_http_429_rate_limit(broker_setup):
    """Test 9: HTTP 429 triggers bounded rate-limit backoff."""
    oms, portfolio, broker, adapter = broker_setup
    cat = adapter.classify_error(ConnectionError("HTTP 429 Too Many Requests"), request_sent=True)
    assert cat == BrokerErrorCategory.RATE_LIMITED


def test_10_http_500_server_error(broker_setup):
    """Test 10: HTTP 500 post-send is classified as EXECUTION_UNCERTAIN."""
    oms, portfolio, broker, adapter = broker_setup
    cat = adapter.classify_error(ConnectionError("HTTP 500 Internal Server Error"), request_sent=True)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN


def test_11_http_502_bad_gateway(broker_setup):
    """Test 11: HTTP 502 Bad Gateway post-send enters UNKNOWN."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.HTTP_502_BAD_GATEWAY)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN
    assert order.state == OrderState.UNKNOWN


def test_12_http_503_service_unavailable(broker_setup):
    """Test 12: HTTP 503 Service Unavailable post-send enters UNKNOWN."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.HTTP_503_SERVICE_UNAVAILABLE)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN
    assert order.state == OrderState.UNKNOWN


def test_13_http_504_gateway_timeout(broker_setup):
    """Test 13: HTTP 504 Gateway Timeout post-send enters UNKNOWN."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.HTTP_504_GATEWAY_TIMEOUT)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN
    assert order.state == OrderState.UNKNOWN


def test_14_malformed_success_response(broker_setup):
    """Test 14: HTTP 200 with malformed JSON post-send enters UNKNOWN."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.MALFORMED_SUCCESS_RESPONSE)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN
    assert order.state == OrderState.UNKNOWN


def test_15_missing_broker_order_id(broker_setup):
    """Test 15: Response missing broker order ID post-send enters UNKNOWN."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.MISSING_ORDER_ID)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN
    assert order.state == OrderState.UNKNOWN


# =====================================================================
# Group 3: Status Recovery Tests
# =====================================================================

def test_16_unknown_state_creation(broker_setup):
    """Test 16: UNKNOWN state is created with transition event."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    
    assert order.state == OrderState.UNKNOWN
    assert order.event_history[-1].event_type == OrderEventType.UNCERTAIN


def test_17_unknown_persistence(broker_setup):
    """Test 17: UNKNOWN state is durably persisted to SQLite."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    
    loaded = oms.get_order(order.order_id)
    assert loaded.state == OrderState.UNKNOWN


def test_18_unknown_survives_restart(test_dir):
    """Test 18: UNKNOWN state survives process restart / DB reconnect."""
    db_path = os.path.join(test_dir, "restart_test.db")
    oms = DurablePaperOMS(db_path=db_path)
    portfolio = PaperPortfolioManager(initial_cash=1000.0)
    broker = FakeBroker()
    adapter = BrokerAdapter(oms=oms, portfolio_manager=portfolio, fake_broker=broker)
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    oms.close()
    
    # Simulate restart
    new_oms = DurablePaperOMS(db_path=db_path)
    restored_order = new_oms.get_order(order.order_id)
    assert restored_order.state == OrderState.UNKNOWN
    new_oms.close()


def test_19_broker_resolves_filled(broker_setup):
    """Test 19: UNKNOWN order resolved to FILLED via broker status lookup."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    
    # Recovery lookup
    resolved_order, res, err = adapter.recover_unknown_order(order.order_id)
    assert res == BrokerStatusResult.FOUND_FILLED
    assert resolved_order.state == OrderState.FILLED
    assert portfolio.get_position("BTCUSDT").size == 0.1


def test_20_broker_resolves_rejected(broker_setup):
    """Test 20: UNKNOWN order resolved to REJECTED via broker lookup."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    
    # Force broker state to REJECTED
    bid = broker.client_order_map[order.client_order_id]
    broker.orders[bid].status = "REJECTED"
    
    resolved_order, res, err = adapter.recover_unknown_order(order.order_id)
    assert res == BrokerStatusResult.FOUND_REJECTED
    assert resolved_order.state == OrderState.REJECTED
    assert portfolio.get_position("BTCUSDT").size == 0.0


def test_21_broker_resolves_partially_filled(broker_setup):
    """Test 21: UNKNOWN order resolved to PARTIALLY_FILLED."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=1.0, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    
    bid = broker.client_order_map[order.client_order_id]
    broker.orders[bid].status = "PARTIALLY_FILLED"
    broker.orders[bid].filled_qty = 0.4
    broker.orders[bid].avg_price = 50000.0
    
    resolved_order, res, err = adapter.recover_unknown_order(order.order_id)
    assert res == BrokerStatusResult.FOUND_PARTIALLY_FILLED
    assert resolved_order.state == OrderState.PARTIALLY_FILLED
    assert resolved_order.filled_qty == 0.4
    assert resolved_order.remaining_qty == 0.6
    assert portfolio.get_position("BTCUSDT").size == 0.4


def test_22_broker_resolves_cancelled(broker_setup):
    """Test 22: UNKNOWN order resolved to CANCELLED."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    
    bid = broker.client_order_map[order.client_order_id]
    broker.orders[bid].status = "CANCELLED"
    
    resolved_order, res, err = adapter.recover_unknown_order(order.order_id)
    assert res == BrokerStatusResult.FOUND_CANCELLED
    assert resolved_order.state == OrderState.CANCELLED


def test_23_broker_status_query_failure(broker_setup):
    """Test 23: Status query failure leaves order in UNKNOWN and halts trading."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    
    resolved_order, res, err = adapter.recover_unknown_order(
        order.order_id, status_fault=BrokerFault.STATUS_QUERY_TIMEOUT
    )
    assert res == BrokerStatusResult.UNKNOWN
    assert resolved_order.state == OrderState.UNKNOWN
    assert adapter.is_trading_halted is True


def test_24_persistent_unknown_triggers_halt(broker_setup):
    """Test 24: Persistent uncertainty prevents new orders."""
    oms, portfolio, broker, adapter = broker_setup
    adapter.is_trading_halted = True
    
    order2 = oms.create_order(symbol="ETHUSDT", side="BUY", total_qty=1.0, price=3000.0)
    _, cat, err = adapter.submit_order_safe(order2)
    assert cat == BrokerErrorCategory.RECOVERY_FAILED
    assert err == "TRADING_HALTED"


# =====================================================================
# Group 4: Retry and Concurrency Tests
# =====================================================================

def test_25_safe_pre_send_retry(broker_setup):
    """Test 25: Pre-send retry with transient failure succeeds without duplication."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    attempts = 0
    orig_submit = broker.submit_order
    def flakey_submit(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("Transient DNS error")
        return orig_submit(*args, **kwargs)
        
    broker.submit_order = flakey_submit
    order, cat, err = adapter.submit_order_safe(order)
    
    assert err is None
    assert order.state == OrderState.FILLED
    assert attempts == 2
    assert portfolio.get_position("BTCUSDT").size == 0.1


def test_26_post_send_retry_suppressed(broker_setup):
    """Test 26: Blind retry after post-send timeout is strictly SUPPRESSED."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    order, cat, err = adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    assert cat == BrokerErrorCategory.EXECUTION_UNCERTAIN
    assert broker.request_count == 1 # Exactly 1 request dispatched, zero blind retries!


def test_27_idempotent_retry_same_client_order_id(broker_setup):
    """Test 27: Resubmitting same client_order_id returns existing broker order without duplicate."""
    oms, portfolio, broker, adapter = broker_setup
    cid = "STABLE_CID_001"
    
    res1 = broker.submit_order("BTCUSDT", "BUY", 0.1, 50000.0, client_order_id=cid)
    res2 = broker.submit_order("BTCUSDT", "BUY", 0.1, 50000.0, client_order_id=cid)
    
    assert res1["broker_order_id"] == res2["broker_order_id"]
    assert res2.get("is_duplicate") is True
    assert len(broker.orders) == 1


def test_28_concurrent_retries_safety(test_dir):
    """Test 28: 10 concurrent threads resolving same order produce exactly one execution."""
    db_path = os.path.join(test_dir, "concurrent_test.db")
    oms = DurablePaperOMS(db_path=db_path)
    portfolio = PaperPortfolioManager(initial_cash=1000.0)
    broker = FakeBroker()
    adapter = BrokerAdapter(oms=oms, portfolio_manager=portfolio, fake_broker=broker)
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    
    threads = []
    results = []
    def worker():
        local_adapter = BrokerAdapter(oms=oms, portfolio_manager=portfolio, fake_broker=broker)
        _, res, _ = local_adapter.recover_unknown_order(order.order_id)
        results.append(res)
        
    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    assert all(r == BrokerStatusResult.FOUND_FILLED for r in results)
    assert portfolio.get_position("BTCUSDT").size == 0.1
    oms.close()


# =====================================================================
# Group 5: Cancellation & Fill/Cancel Races
# =====================================================================

def test_29_cancel_success(broker_setup):
    """Test 29: Successful cancellation transitions order to CANCELLED."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    # Setup order in ACKNOWLEDGED state on OMS and OPEN on broker
    bid = f"BINANCE_{uuid.uuid4().hex[:10].upper()}"
    broker.orders[bid] = BrokerOrderRecord(
        broker_order_id=bid,
        client_order_id=order.client_order_id,
        symbol="BTCUSDT",
        side="BUY",
        order_qty=0.1,
        price=50000.0,
        status="OPEN"
    )
    broker.client_order_map[order.client_order_id] = bid
    order.metadata["broker_order_id"] = bid
    PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
    oms.save_transition(order, order.event_history[-1])
    PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
    oms.save_transition(order, order.event_history[-1])

    res_order, status = adapter.cancel_order_safe(order.order_id)
    assert status == "CANCELLED"
    assert res_order.state == OrderState.CANCELLED


def test_30_cancel_timeout_handled(broker_setup):
    """Test 30: Cancel timeout queries broker and recovers state."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order)
    
    res_order, status = adapter.cancel_order_safe(order.order_id, cancel_fault=BrokerFault.CANCEL_TIMEOUT)
    assert status == "RECOVERED_AFTER_CANCEL_TIMEOUT"
    assert res_order.state in (OrderState.FILLED, OrderState.CANCELLED)


def test_31_cancel_fill_race(broker_setup):
    """Test 31: Order filled before cancel arrived -> Resolves to FILLED, not CANCELLED."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    
    # Setup order in ACKNOWLEDGED on OMS and OPEN on broker
    bid = f"BINANCE_{uuid.uuid4().hex[:10].upper()}"
    broker.orders[bid] = BrokerOrderRecord(
        broker_order_id=bid,
        client_order_id=order.client_order_id,
        symbol="BTCUSDT",
        side="BUY",
        order_qty=0.1,
        price=50000.0,
        status="OPEN"
    )
    broker.client_order_map[order.client_order_id] = bid
    order.metadata["broker_order_id"] = bid
    PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
    oms.save_transition(order, order.event_history[-1])
    PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
    oms.save_transition(order, order.event_history[-1])
    
    res_order, status = adapter.cancel_order_safe(order.order_id, cancel_fault=BrokerFault.CANCEL_FILL_RACE)
    assert status == "FILLED_RACE"
    assert res_order.state == OrderState.FILLED
    assert portfolio.get_position("BTCUSDT").size == 0.1


# =====================================================================
# Group 6: Critical Scenarios & State Equivalence
# =====================================================================

def test_critical_01_lost_response_after_broker_execution(broker_setup):
    """
    Critical Scenario 1: Lost response after broker execution.
    Verifies: 1 logical order, 1 broker order, 1 execution, 1 position mutation.
    """
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    
    adapter.submit_order_safe(order, injected_fault=BrokerFault.LOST_RESPONSE_AFTER_SEND)
    assert order.state == OrderState.UNKNOWN
    assert portfolio.get_position("BTCUSDT").size == 0.0
    
    resolved_order, res, _ = adapter.recover_unknown_order(order.order_id)
    assert res == BrokerStatusResult.FOUND_FILLED
    assert resolved_order.state == OrderState.FILLED
    assert portfolio.get_position("BTCUSDT").size == 0.5
    assert len(broker.orders) == 1


def test_critical_02_unknown_to_rejected(broker_setup):
    """Critical Scenario 2: UNKNOWN order resolved to REJECTED produces zero economic mutation."""
    oms, portfolio, broker, adapter = broker_setup
    init_cash = portfolio.cash
    order = oms.create_order(symbol="ETHUSDT", side="BUY", total_qty=1.0, price=3000.0)
    
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    bid = broker.client_order_map[order.client_order_id]
    broker.orders[bid].status = "REJECTED"
    
    resolved_order, res, _ = adapter.recover_unknown_order(order.order_id)
    assert res == BrokerStatusResult.FOUND_REJECTED
    assert resolved_order.state == OrderState.REJECTED
    assert portfolio.cash == init_cash
    assert portfolio.get_position("ETHUSDT").size == 0.0


def test_critical_03_unknown_to_partially_filled(broker_setup):
    """Critical Scenario 3: UNKNOWN order resolved to PARTIALLY_FILLED updates quantity and VWAP."""
    oms, portfolio, broker, adapter = broker_setup
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=1.0, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    
    bid = broker.client_order_map[order.client_order_id]
    broker.orders[bid].status = "PARTIALLY_FILLED"
    broker.orders[bid].filled_qty = 0.4
    broker.orders[bid].avg_price = 50000.0
    
    resolved_order, res, _ = adapter.recover_unknown_order(order.order_id)
    assert res == BrokerStatusResult.FOUND_PARTIALLY_FILLED
    assert resolved_order.filled_qty == 0.4
    assert resolved_order.remaining_qty == 0.6
    assert portfolio.get_position("BTCUSDT").size == 0.4


def test_critical_04_unknown_survives_crash_and_recovers(test_dir):
    """Critical Scenario 4: UNKNOWN state survives crash and recovers after restart."""
    db_path = os.path.join(test_dir, "crash_test.db")
    oms = DurablePaperOMS(db_path=db_path)
    portfolio = PaperPortfolioManager(initial_cash=1000.0)
    broker = FakeBroker()
    adapter = BrokerAdapter(oms=oms, portfolio_manager=portfolio, fake_broker=broker)
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    assert order.state == OrderState.UNKNOWN
    oms.close()
    
    # Process crash & restart
    new_oms = DurablePaperOMS(db_path=db_path)
    new_portfolio = PaperPortfolioManager(initial_cash=1000.0)
    new_adapter = BrokerAdapter(oms=new_oms, portfolio_manager=new_portfolio, fake_broker=broker)
    
    restored_order = new_oms.get_order(order.order_id)
    assert restored_order.state == OrderState.UNKNOWN
    
    # Resolve after restart
    resolved_order, res, _ = new_adapter.recover_unknown_order(restored_order.order_id)
    assert res == BrokerStatusResult.FOUND_FILLED
    assert resolved_order.state == OrderState.FILLED
    assert new_portfolio.get_position("BTCUSDT").size == 0.1
    new_oms.close()


def test_critical_05_state_equivalence_normal_vs_fault_recovered(test_dir):
    """
    Critical Scenario 5: State Equivalence Test.
    Path A (Normal Execution) == Path B (Fault-Injected & Recovered Execution).
    """
    # Path A: Normal Execution
    path1 = os.path.join(test_dir, "path_a.db")
    oms_a = DurablePaperOMS(db_path=path1)
    port_a = PaperPortfolioManager(initial_cash=1000.0)
    broker_a = FakeBroker()
    adapter_a = BrokerAdapter(oms_a, port_a, broker_a)
    
    ord_a = oms_a.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.2, price=50000.0)
    adapter_a.submit_order_safe(ord_a)
    oms_a.close()
    
    # Path B: Injected Timeout + Restart + Recovery
    path2 = os.path.join(test_dir, "path_b.db")
    oms_b = DurablePaperOMS(db_path=path2)
    port_b = PaperPortfolioManager(initial_cash=1000.0)
    broker_b = FakeBroker()
    adapter_b = BrokerAdapter(oms_b, port_b, broker_b)
    
    ord_b = oms_b.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.2, price=50000.0)
    adapter_b.submit_order_safe(ord_b, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    oms_b.close()
    
    # Crash & Restart
    oms_b_restarted = DurablePaperOMS(db_path=path2)
    port_b_restarted = PaperPortfolioManager(initial_cash=1000.0)
    adapter_b_restarted = BrokerAdapter(oms_b_restarted, port_b_restarted, broker_b)
    adapter_b_restarted.recover_unknown_order(ord_b.order_id)
    
    # Assert Exact Economic Equivalence
    assert port_a.cash == port_b_restarted.cash
    assert port_a.get_position("BTCUSDT").size == port_b_restarted.get_position("BTCUSDT").size
    assert port_a.get_position("BTCUSDT").entry_price == port_b_restarted.get_position("BTCUSDT").entry_price
    assert port_a.compute_state_checksum() == port_b_restarted.compute_state_checksum()
    oms_b_restarted.close()


def test_critical_06_multi_restart_recovery(test_dir):
    """Critical Scenario 6: Multi-restart recovery handles repeated transient failures."""
    db_path = os.path.join(test_dir, "multi_restart.db")
    oms = DurablePaperOMS(db_path=db_path)
    port = PaperPortfolioManager(initial_cash=1000.0)
    broker = FakeBroker()
    adapter = BrokerAdapter(oms, port, broker)
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    oms.close()
    
    # Restart 1: Status query fails
    oms1 = DurablePaperOMS(db_path=db_path)
    port1 = PaperPortfolioManager(initial_cash=1000.0)
    adapter1 = BrokerAdapter(oms1, port1, broker)
    adapter1.recover_unknown_order(order.order_id, status_fault=BrokerFault.STATUS_QUERY_TIMEOUT)
    assert oms1.get_order(order.order_id).state == OrderState.UNKNOWN
    oms1.close()
    broker.clear_faults()
    
    # Restart 2: Status query succeeds
    oms2 = DurablePaperOMS(db_path=db_path)
    port2 = PaperPortfolioManager(initial_cash=1000.0)
    adapter2 = BrokerAdapter(oms2, port2, broker)
    adapter2.recover_unknown_order(order.order_id)
    assert oms2.get_order(order.order_id).state == OrderState.FILLED
    assert port2.get_position("BTCUSDT").size == 0.1
    oms2.close()
