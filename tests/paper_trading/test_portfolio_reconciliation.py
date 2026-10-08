"""
P2-7: Automated Portfolio Reconciliation, Broker Truth Verification & Safe Trading Halt Test Suite
=================================================================================================
Validates continuous reconciliation, broker truth verification, tolerance models, direction inversion,
orphan order detection, missing execution repair, crash recovery startup validation, and fail-closed trading gates.
"""

import os
import uuid
import shutil
import pytest
import sqlite3
import tempfile
import threading
from typing import Dict, Any, List
from decimal import Decimal

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
    PaperPosition,
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
from reconciliation.portfolio_reconciler import (
    DriftSeverity,
    DriftType,
    ReconciliationStatus,
    HaltScope,
    ReconciliationMode,
    ReconciliationTolerance,
    DriftItem,
    PortfolioReconciler
)


@pytest.fixture
def recon_setup():
    """Provides isolated DurablePaperOMS, PaperPortfolioManager, FakeBroker, BrokerAdapter, and PortfolioReconciler."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, f"test_recon_{uuid.uuid4().hex[:8]}.db")
    oms = DurablePaperOMS(db_path=db_path)
    portfolio = PaperPortfolioManager(initial_cash=100000.0, fee_rate=0.0004)
    broker = FakeBroker(initial_cash=100000.0, fee_rate=0.0004)
    adapter = BrokerAdapter(oms, portfolio, broker)
    reconciler = PortfolioReconciler(oms, portfolio, broker, adapter)

    yield oms, portfolio, broker, adapter, reconciler

    oms.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# =====================================================================
# Group 1: Position Reconciliation & Direction Inversion
# =====================================================================

def test_01_perfect_position_match(recon_setup):
    """Test 1: Perfectly matching positions produce HEALTHY status and zero drift."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    # Fill BTC order on both internal and broker
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    adapter.submit_order_safe(order)
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.HEALTHY
    assert snap.drift_count == 0
    assert reconciler.is_trading_halted is False


def test_02_long_position_mismatch(recon_setup):
    """Test 2: Internal 0.5 BTC vs Broker 0.6 BTC generates CRITICAL position drift and halts BTC."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    adapter.submit_order_safe(order)
    
    # Inject broker position drift
    broker.set_position("BTCUSDT", size=0.6, side="LONG", entry_price=50000.0)
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    assert snap.drift_count >= 1
    assert any(d.drift_type == DriftType.POSITION_QTY_MISMATCH and d.symbol == "BTCUSDT" for d in snap.drifts)
    assert reconciler.is_trading_halted is True
    assert "BTCUSDT" in reconciler.halted_symbols


def test_03_short_position_mismatch(recon_setup):
    """Test 3: Short position mismatch is detected."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    portfolio.positions["ETHUSDT"] = PaperPosition("ETHUSDT", PositionSide.SHORT, size=2.0, entry_price=3000.0)
    broker.set_position("ETHUSDT", size=3.0, side="SHORT", entry_price=3000.0)
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    assert any(d.symbol == "ETHUSDT" and d.drift_type == DriftType.POSITION_QTY_MISMATCH for d in snap.drifts)


def test_04_direction_inversion(recon_setup):
    """Test 4: Internal LONG +0.5 vs Broker SHORT -0.5 triggers POSITION_SIDE_MISMATCH critical drift."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    portfolio.positions["SOLUSDT"] = PaperPosition("SOLUSDT", PositionSide.LONG, size=10.0, entry_price=150.0)
    broker.set_position("SOLUSDT", size=10.0, side="SHORT", entry_price=150.0)
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    assert any(d.drift_type == DriftType.POSITION_SIDE_MISMATCH and d.symbol == "SOLUSDT" for d in snap.drifts)


def test_05_flat_account_match(recon_setup):
    """Test 5: Flat positions (0.0 == 0.0) across all assets evaluate to HEALTHY."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.HEALTHY
    assert snap.drift_count == 0


def test_06_quantity_within_tolerance(recon_setup):
    """Test 6: Tiny floating delta below tolerance (e.g. 1e-8) matches without drift."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    portfolio.positions["BTCUSDT"] = PaperPosition("BTCUSDT", PositionSide.LONG, size=1.00000001, entry_price=50000.0)
    broker.set_position("BTCUSDT", size=1.00000002, side="LONG", entry_price=50000.0)
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.HEALTHY
    assert snap.drift_count == 0


def test_07_quantity_outside_tolerance(recon_setup):
    """Test 7: Delta exceeding quantity tolerance (0.001) triggers drift."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    portfolio.positions["BTCUSDT"] = PaperPosition("BTCUSDT", PositionSide.LONG, size=1.0, entry_price=50000.0)
    broker.set_position("BTCUSDT", size=1.005, side="LONG", entry_price=50000.0)
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT


# =====================================================================
# Group 2: Cash & Balance Reconciliation
# =====================================================================

def test_08_cash_match(recon_setup):
    """Test 8: Matching cash produces clean balance summary."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    snap = reconciler.reconcile(mode=ReconciliationMode.ACCOUNT)
    assert snap.balance_summary["matched"] is True
    assert snap.status == ReconciliationStatus.HEALTHY


def test_09_cash_mismatch(recon_setup):
    """Test 9: Internal $100,000 vs Broker $94,000 generates BALANCE_MISMATCH and ACCOUNT halt."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    broker.set_balance(available_cash=94000.0, total_equity=94000.0)
    snap = reconciler.reconcile(mode=ReconciliationMode.ACCOUNT)
    
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    assert any(d.drift_type == DriftType.BALANCE_MISMATCH for d in snap.drifts)
    assert reconciler.halt_scope == HaltScope.ACCOUNT
    assert reconciler.is_trading_halted is True


# =====================================================================
# Group 3: Order Reconciliation & Orphan Orders
# =====================================================================

def test_10_internal_open_order_missing_at_broker(recon_setup):
    """Test 10: Open internal order missing at broker triggers ORDER_MISSING_AT_BROKER."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    # Create order in OMS without submitting to broker
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
    oms.save_transition(order, order.event_history[-1])
    
    snap = reconciler.reconcile()
    assert any(d.drift_type == DriftType.ORDER_MISSING_AT_BROKER for d in snap.drifts)


def test_11_orphan_broker_order(recon_setup):
    """Test 11: Untracked open broker order triggers ORPHAN_BROKER_ORDER critical drift."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    orphan_id = broker.add_orphan_order(symbol="BTCUSDT", side="BUY", qty=0.5, price=50000.0, status="OPEN")
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    assert any(d.drift_type == DriftType.ORPHAN_BROKER_ORDER and d.order_id == orphan_id for d in snap.drifts)
    assert reconciler.is_trading_halted is True


def test_12_order_status_mismatch(recon_setup):
    """Test 12: Internal ACKNOWLEDGED vs Broker PARTIALLY_FILLED triggers status/fill mismatch."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=1.0, price=50000.0)
    PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
    oms.save_transition(order, order.event_history[-1])
    PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
    oms.save_transition(order, order.event_history[-1])
    
    bid = f"BINANCE_{uuid.uuid4().hex[:10].upper()}"
    broker.orders[bid] = BrokerOrderRecord(
        broker_order_id=bid,
        client_order_id=order.client_order_id,
        symbol="BTCUSDT",
        side="BUY",
        order_qty=1.0,
        filled_qty=0.4,
        status="PARTIALLY_FILLED"
    )
    broker.client_order_map[order.client_order_id] = bid
    
    snap = reconciler.reconcile()
    assert any(d.drift_type == DriftType.FILL_QTY_MISMATCH or d.drift_type == DriftType.ORDER_STATUS_MISMATCH for d in snap.drifts)


# =====================================================================
# Group 4: Execution Reconciliation & Missing Fills
# =====================================================================

def test_14_broker_execution_missing_internally(recon_setup):
    """Test 14: Confirmed broker execution missing internally triggers MISSING_INTERNAL_EXECUTION."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    exec_id = f"EXEC_ORPHAN_{uuid.uuid4().hex[:8]}"
    broker.add_orphan_execution(
        execution_id=exec_id,
        symbol="BTCUSDT",
        side="BUY",
        fill_qty=0.25,
        fill_price=50000.0,
        fee=5.0
    )
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    assert any(d.drift_type == DriftType.MISSING_INTERNAL_EXECUTION and d.execution_id == exec_id for d in snap.drifts)


def test_15_internal_execution_unavailable_at_broker(recon_setup):
    """Test 15: Internal execution not returned by broker trade history flagged as WARNING."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    oms.execute_order(order.order_id, fill_price=50000.0, fill_qty=0.1, fee=2.0, execution_id="EXEC_INTERNAL_ONLY")
    portfolio.apply_order_fill(order, 0.1, 50000.0, 2.0, "EXEC_INTERNAL_ONLY")
    
    snap = reconciler.reconcile()
    assert any(d.drift_type == DriftType.MISSING_BROKER_EXECUTION and d.execution_id == "EXEC_INTERNAL_ONLY" for d in snap.drifts)


def test_16_duplicate_execution_deduplication(recon_setup):
    """Test 16: Duplicate executions returned by broker are deduplicated safely."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order)
    
    # Duplicate execution in broker list
    bid = broker.client_order_map[order.client_order_id]
    orig_exec = broker.orders[bid].executions[0]
    broker.orders[bid].executions.append(dict(orig_exec))
    
    snap = reconciler.reconcile()
    assert snap.execution_summary["missing_internally"] == 0


def test_17_fill_quantity_mismatch(recon_setup):
    """Test 17: Fill quantity mismatch between order executions and records is caught."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=1.0, price=50000.0)
    adapter.submit_order_safe(order)
    
    # Tamper execution quantity on broker
    bid = broker.client_order_map[order.client_order_id]
    broker.orders[bid].executions[0]["fill_qty"] = 0.99
    
    snap = reconciler.reconcile()
    assert any(d.drift_type == DriftType.FILL_QTY_MISMATCH for d in snap.drifts)


# =====================================================================
# Group 5: Broker API Failures & Fail-Closed Safety
# =====================================================================

def test_21_broker_position_query_timeout(recon_setup):
    """Test 21: Position query timeout triggers DATA_UNAVAILABLE and halts trading."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    broker.inject_fault(BrokerFault.RECON_POSITIONS_TIMEOUT)
    snap = reconciler.reconcile()
    
    assert snap.status == ReconciliationStatus.DATA_UNAVAILABLE
    assert reconciler.is_trading_halted is True
    assert reconciler.halt_scope == HaltScope.GLOBAL


def test_22_broker_balance_query_timeout(recon_setup):
    """Test 22: Balance query timeout triggers DATA_UNAVAILABLE and halts trading."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    broker.inject_fault(BrokerFault.RECON_BALANCES_TIMEOUT)
    snap = reconciler.reconcile()
    
    assert snap.status == ReconciliationStatus.DATA_UNAVAILABLE
    assert reconciler.is_trading_halted is True


def test_26_stale_broker_data(recon_setup):
    """Test 26: Stale broker snapshot timestamp triggers BROKER_DATA_STALE and halts trading."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    broker.inject_fault(BrokerFault.RECON_DATA_STALE)
    snap = reconciler.reconcile()
    
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    assert any(d.drift_type == DriftType.BROKER_DATA_STALE for d in snap.drifts)
    assert reconciler.is_trading_halted is True


# =====================================================================
# Group 6: Safe Execution Import & Repair
# =====================================================================

def test_36_safe_execution_repair(recon_setup):
    """Test 36: Missing broker execution is safely imported, applying fill and restoring HEALTHY status."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    exec_id = f"EXEC_REPAIR_{uuid.uuid4().hex[:8]}"
    
    # Inject missing fill on broker
    broker.orders["BINANCE_B1"] = BrokerOrderRecord(
        broker_order_id="BINANCE_B1",
        client_order_id=order.client_order_id,
        symbol="BTCUSDT",
        side="BUY",
        order_qty=0.5,
        filled_qty=0.5,
        price=50000.0,
        avg_price=50000.0,
        status="FILLED",
        executions=[{
            "execution_id": exec_id,
            "fill_price": 50000.0,
            "fill_qty": 0.5,
            "fee": 10.0,
            "timestamp": "2026-10-07T12:00:00+00:00"
        }]
    )
    broker.client_order_map[order.client_order_id] = "BINANCE_B1"
    
    # Reconcile detects critical drift
    snap1 = reconciler.reconcile()
    assert snap1.status == ReconciliationStatus.CRITICAL_DRIFT
    assert reconciler.is_trading_halted is True
    
    # Safe repair
    success, msg = reconciler.safe_repair_execution(
        execution_id=exec_id,
        broker_exec_data={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "fill_qty": 0.5,
            "fill_price": 50000.0,
            "fee": 10.0,
            "client_order_id": order.client_order_id
        }
    )
    assert success is True
    assert reconciler.is_trading_halted is False
    assert portfolio.get_position("BTCUSDT").size == 0.5
    assert oms.get_order(order.order_id).state == OrderState.FILLED


def test_37_duplicate_repair_request(recon_setup):
    """Test 37: Repeated repair requests for same execution ID are idempotent no-ops."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.2, price=50000.0)
    exec_id = "EXEC_DUP_TEST"
    
    broker_exec = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "fill_qty": 0.2,
        "fill_price": 50000.0,
        "fee": 4.0,
        "client_order_id": order.client_order_id
    }
    
    # First repair
    success1, _ = reconciler.safe_repair_execution(exec_id, broker_exec)
    assert success1 is True
    
    # Second repair (duplicate)
    success2, msg2 = reconciler.safe_repair_execution(exec_id, broker_exec)
    assert success2 is True
    assert msg2 == "ALREADY_APPLIED"
    assert portfolio.get_position("BTCUSDT").size == 0.2 # No double fill


# =====================================================================
# Group 7: Concurrency & Multi-Worker Safety
# =====================================================================

def test_38_concurrent_reconciliation(recon_setup):
    """Test 38: Multiple concurrent reconciliation workers execute deterministically without race conditions."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order)
    
    errors = []
    snapshots = []
    def worker():
        try:
            snap = reconciler.reconcile()
            snapshots.append(snap)
        except Exception as e:
            errors.append(e)
            
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    assert len(errors) == 0
    assert len(snapshots) == 10
    assert all(s.status == ReconciliationStatus.HEALTHY for s in snapshots)


# =====================================================================
# Group 8: Critical Scenario Suite (Requirements 60-67)
# =====================================================================

def test_critical_01_broker_position_drift(recon_setup):
    """Critical Scenario 1: Position drift halts affected asset without automatic overwrite."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    portfolio.positions["BTCUSDT"] = PaperPosition("BTCUSDT", PositionSide.LONG, size=0.50, entry_price=50000.0)
    broker.set_position("BTCUSDT", size=0.60, side="LONG", entry_price=50000.0)
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    assert "BTCUSDT" in reconciler.halted_symbols
    assert portfolio.get_position("BTCUSDT").size == 0.50 # NOT overwritten!


def test_critical_02_orphan_broker_order(recon_setup):
    """Critical Scenario 2: Orphan broker order triggers critical drift and safety halt."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    orphan_id = broker.add_orphan_order(symbol="ETHUSDT", side="BUY", qty=1.0, price=3000.0)
    snap = reconciler.reconcile()
    
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    assert reconciler.is_trading_halted is True
    assert any(d.drift_type == DriftType.ORPHAN_BROKER_ORDER for d in snap.drifts)


def test_critical_03_missing_internal_execution(recon_setup):
    """Critical Scenario 3: Missing internal execution repaired with authoritative evidence."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    exec_id = "EXEC_C3"
    
    broker.orders["B_C3"] = BrokerOrderRecord(
        broker_order_id="B_C3",
        client_order_id=order.client_order_id,
        symbol="BTCUSDT",
        side="BUY",
        order_qty=0.5,
        filled_qty=0.5,
        price=50000.0,
        avg_price=50000.0,
        status="FILLED",
        executions=[{"execution_id": exec_id, "fill_price": 50000.0, "fill_qty": 0.5, "fee": 10.0, "timestamp": "2026-10-07T12:00:00+00:00"}]
    )
    broker.client_order_map[order.client_order_id] = "B_C3"
    
    # Reconcile detects drift
    snap_before = reconciler.reconcile()
    assert snap_before.status == ReconciliationStatus.CRITICAL_DRIFT
    
    # Repair
    success, _ = reconciler.safe_repair_execution(
        exec_id,
        {"symbol": "BTCUSDT", "side": "BUY", "fill_qty": 0.5, "fill_price": 50000.0, "fee": 10.0, "client_order_id": order.client_order_id}
    )
    assert success is True
    
    snap_after = reconciler.reconcile()
    assert snap_after.status == ReconciliationStatus.HEALTHY
    assert reconciler.is_trading_halted is False


def test_critical_04_unknown_order_recovery(recon_setup):
    """Critical Scenario 4: UNKNOWN order resolved to FILLED via broker query matches portfolio."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.2, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    assert oms.get_order(order.order_id).state == OrderState.UNKNOWN
    
    # Reconcile resolves UNKNOWN via broker query
    adapter.recover_unknown_order(order.order_id)
    assert oms.get_order(order.order_id).state == OrderState.FILLED
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.HEALTHY


def test_critical_05_partial_fill_drift(recon_setup):
    """Critical Scenario 5: Partial fill discrepancy 0.4 vs 0.6 repaired without overfill."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=1.0, price=50000.0)
    oms.execute_order(order.order_id, fill_price=50000.0, fill_qty=0.4, fee=8.0, execution_id="EX_01")
    portfolio.apply_order_fill(order, 0.4, 50000.0, 8.0, "EX_01")
    
    # Broker has 0.6 fill across 2 executions
    broker.orders["B_P5"] = BrokerOrderRecord(
        broker_order_id="B_P5",
        client_order_id=order.client_order_id,
        symbol="BTCUSDT",
        side="BUY",
        order_qty=1.0,
        filled_qty=0.6,
        price=50000.0,
        avg_price=50000.0,
        status="PARTIALLY_FILLED",
        executions=[
            {"execution_id": "EX_01", "fill_price": 50000.0, "fill_qty": 0.4, "fee": 8.0, "timestamp": "2026-10-07T12:00:00+00:00"},
            {"execution_id": "EX_02", "fill_price": 50000.0, "fill_qty": 0.2, "fee": 4.0, "timestamp": "2026-10-07T12:05:00+00:00"}
        ]
    )
    broker.client_order_map[order.client_order_id] = "B_P5"
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    
    # Import missing 0.2 fill
    reconciler.safe_repair_execution(
        "EX_02",
        {"symbol": "BTCUSDT", "side": "BUY", "fill_qty": 0.2, "fill_price": 50000.0, "fee": 4.0, "client_order_id": order.client_order_id}
    )
    
    snap_post = reconciler.reconcile()
    assert snap_post.status == ReconciliationStatus.HEALTHY
    assert round(portfolio.get_position("BTCUSDT").size, 6) == 0.6


def test_critical_06_broker_api_unavailable(recon_setup):
    """Critical Scenario 6: All broker queries timing out returns DATA_UNAVAILABLE and halts."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    broker.inject_fault(BrokerFault.RECON_POSITIONS_TIMEOUT)
    broker.inject_fault(BrokerFault.RECON_BALANCES_TIMEOUT)
    broker.inject_fault(BrokerFault.RECON_ORDERS_TIMEOUT)
    broker.inject_fault(BrokerFault.RECON_EXECUTIONS_TIMEOUT)
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.DATA_UNAVAILABLE
    assert reconciler.is_trading_halted is True
    assert snap.drift_count >= 1


def test_critical_07_startup_safety_halt_on_drift(test_dir):
    """Critical Scenario 7: Startup replay succeeds but broker drift halts trading before resumption."""
    db_path = os.path.join(test_dir, "startup_drift.db")
    oms = DurablePaperOMS(db_path=db_path)
    portfolio = PaperPortfolioManager(initial_cash=100000.0)
    broker = FakeBroker(initial_cash=100000.0)
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    oms.execute_order(order.order_id, fill_price=50000.0, fill_qty=0.5, fee=10.0, execution_id="EX_S1")
    portfolio.apply_order_fill(order, 0.5, 50000.0, 10.0, "EX_S1")
    oms.close()
    
    # Broker has different position (0.7 BTC)
    broker.set_position("BTCUSDT", size=0.7, side="LONG", entry_price=50000.0)
    
    # Process Restart
    oms_restart = DurablePaperOMS(db_path=db_path)
    port_restart = PaperPortfolioManager(initial_cash=100000.0)
    reconciler_restart = PortfolioReconciler(oms_restart, port_restart, broker)
    
    permitted, snap = reconciler_restart.startup_reconciliation()
    assert permitted is False
    assert reconciler_restart.is_trading_halted is True
    assert snap.status == ReconciliationStatus.CRITICAL_DRIFT
    oms_restart.close()


def test_critical_08_crash_during_repair_recovery(test_dir):
    """Critical Scenario 8: Crash during repair recovers safely on restart with zero duplicate fills."""
    db_path = os.path.join(test_dir, "repair_crash.db")
    oms = DurablePaperOMS(db_path=db_path)
    portfolio = PaperPortfolioManager(initial_cash=100000.0)
    broker = FakeBroker(initial_cash=100000.0)
    reconciler = PortfolioReconciler(oms, portfolio, broker)
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    exec_id = "EX_CRASH_TEST"
    
    # Broker has execution
    broker.orders["B_CRASH"] = BrokerOrderRecord(
        broker_order_id="B_CRASH",
        client_order_id=order.client_order_id,
        symbol="BTCUSDT",
        side="BUY",
        order_qty=0.5,
        filled_qty=0.5,
        price=50000.0,
        avg_price=50000.0,
        status="FILLED",
        executions=[{"execution_id": exec_id, "fill_price": 50000.0, "fill_qty": 0.5, "fee": 10.0, "timestamp": "2026-10-07T12:00:00+00:00"}]
    )
    broker.client_order_map[order.client_order_id] = "B_CRASH"
    
    # Perform repair
    reconciler.safe_repair_execution(
        exec_id,
        {"symbol": "BTCUSDT", "side": "BUY", "fill_qty": 0.5, "fill_price": 50000.0, "fee": 10.0, "client_order_id": order.client_order_id}
    )
    oms.close()
    
    # Restart
    oms_restarted = DurablePaperOMS(db_path=db_path)
    port_restarted = PaperPortfolioManager(initial_cash=100000.0)
    reconciler_restarted = PortfolioReconciler(oms_restarted, port_restarted, broker)
    
    permitted, snap = reconciler_restarted.startup_reconciliation()
    assert permitted is True
    assert snap.status == ReconciliationStatus.HEALTHY
    assert port_restarted.get_position("BTCUSDT").size == 0.5
    oms_restarted.close()


# =====================================================================
# Group 9: Additional Domain Verifications & Scope Testing
# =====================================================================

def test_18_vwap_and_price_mismatch(recon_setup):
    """Test 18: Discrepancy in execution fill prices triggers PRICE_MISMATCH."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    oms.execute_order(order.order_id, fill_price=50000.0, fill_qty=0.5, fee=10.0, execution_id="EX_P18")
    portfolio.apply_order_fill(order, 0.5, 50000.0, 10.0, "EX_P18")
    
    broker.orders["B_P18"] = BrokerOrderRecord(
        broker_order_id="B_P18",
        client_order_id=order.client_order_id,
        symbol="BTCUSDT",
        side="BUY",
        order_qty=0.5,
        filled_qty=0.5,
        price=51000.0,
        avg_price=51000.0,
        status="FILLED",
        executions=[{"execution_id": "EX_P18", "fill_price": 51000.0, "fill_qty": 0.5, "fee": 10.0, "timestamp": "2026-10-07T12:00:00+00:00"}]
    )
    broker.client_order_map[order.client_order_id] = "B_P18"
    
    snap = reconciler.reconcile()
    assert any(d.drift_type == DriftType.PRICE_MISMATCH for d in snap.drifts)


def test_19_fee_mismatch(recon_setup):
    """Test 19: Discrepancy in execution fees outside tolerance triggers FEE_MISMATCH."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    oms.execute_order(order.order_id, fill_price=50000.0, fill_qty=0.5, fee=10.0, execution_id="EX_F19")
    portfolio.apply_order_fill(order, 0.5, 50000.0, 10.0, "EX_F19")
    
    broker.orders["B_F19"] = BrokerOrderRecord(
        broker_order_id="B_F19",
        client_order_id=order.client_order_id,
        symbol="BTCUSDT",
        side="BUY",
        order_qty=0.5,
        filled_qty=0.5,
        price=50000.0,
        avg_price=50000.0,
        status="FILLED",
        executions=[{"execution_id": "EX_F19", "fill_price": 50000.0, "fill_qty": 0.5, "fee": 15.0, "timestamp": "2026-10-07T12:00:00+00:00"}]
    )
    broker.client_order_map[order.client_order_id] = "B_F19"
    
    snap = reconciler.reconcile()
    assert any(d.drift_type == DriftType.FEE_MISMATCH for d in snap.drifts)


def test_25_partial_broker_api_failure(recon_setup):
    """Test 25: Partial broker API failure (orders timeout) identifies failed domain and halts safely."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    broker.inject_fault(BrokerFault.RECON_ORDERS_TIMEOUT)
    snap = reconciler.reconcile()
    
    assert snap.status == ReconciliationStatus.DATA_UNAVAILABLE
    assert any(d.domain == "ORDERS" and d.drift_type == DriftType.BROKER_DATA_UNAVAILABLE for d in snap.drifts)
    assert reconciler.is_trading_halted is True


def test_28_unknown_order_to_filled(recon_setup):
    """Test 28: Order in UNKNOWN state resolved to FILLED via broker query."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.1, price=50000.0)
    adapter.submit_order_safe(order, injected_fault=BrokerFault.TIMEOUT_AFTER_SEND)
    assert oms.get_order(order.order_id).state == OrderState.UNKNOWN
    
    adapter.recover_unknown_order(order.order_id)
    assert oms.get_order(order.order_id).state == OrderState.FILLED
    
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.HEALTHY


def test_34_symbol_level_halt_scope(recon_setup):
    """Test 34: Position drift on BTC only halts BTC, leaving other symbols untouched."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    portfolio.positions["BTCUSDT"] = PaperPosition("BTCUSDT", PositionSide.LONG, size=0.5, entry_price=50000.0)
    broker.set_position("BTCUSDT", size=0.6, side="LONG", entry_price=50000.0)
    
    snap = reconciler.reconcile()
    assert snap.halt_scope == HaltScope.SYMBOL
    assert "BTCUSDT" in reconciler.halted_symbols
    assert "ETHUSDT" not in reconciler.halted_symbols


def test_35_account_level_halt_scope(recon_setup):
    """Test 35: Account cash balance drift triggers ACCOUNT halt scope."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    broker.set_balance(available_cash=50000.0, total_equity=50000.0)
    snap = reconciler.reconcile()
    
    assert snap.halt_scope == HaltScope.ACCOUNT
    assert reconciler.is_trading_halted is True


def test_49_multi_asset_13_universe_reconciliation(recon_setup):
    """Test 49: Reconciles all 13 canonical crypto universe assets accurately."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    # Setup positions across multi-asset universe
    universe = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT"]
    for sym in universe[:5]:
        order = oms.create_order(symbol=sym, side="BUY", total_qty=1.0, price=100.0)
        adapter.submit_order_safe(order)
        
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.HEALTHY
    assert snap.position_summary["total_symbols_evaluated"] >= 13
    assert snap.drift_count == 0


def test_50_p2_regressions_preserved(recon_setup):
    """Test 50: P2-1 through P2-6 lifecycle and idempotency contracts remain 100% intact."""
    oms, portfolio, broker, adapter, reconciler = recon_setup
    
    # 1. State machine & idempotency
    order = oms.create_order(symbol="BTCUSDT", side="BUY", total_qty=0.5, price=50000.0)
    order, cat, err = adapter.submit_order_safe(order)
    assert order.state == OrderState.FILLED
    assert err is None
    
    # 2. Overfill protection
    with pytest.raises(Exception):
        oms.execute_order(order.order_id, fill_price=50000.0, fill_qty=0.5)
        
    # 3. Reconciliation verification
    snap = reconciler.reconcile()
    assert snap.status == ReconciliationStatus.HEALTHY
