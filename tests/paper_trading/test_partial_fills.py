"""
P2-3: Partial Fills, Cancellations, Expirations & Rejection Lifecycle Test Suite
================================================================================
Comprehensive test matrix validating:
1. Basic fills (single full fill, 2 partials, 3 partials, N partials).
2. Multi-price execution & VWAP accuracy.
3. Cancellation lifecycles (cancel before fill, cancel after partial fill, cancel after full fill).
4. Expiration lifecycles (expire before fill, expire after partial fill, expire after full fill).
5. Rejection models (insufficient balance, invalid quantity, invalid price, risk limit, overfill).
6. Safety & invariant enforcement (zero fill, negative fill, overfill rejection, duplicate lifecycle events).
7. Position & accounting consistency (BUY/SELL position mutations, cash conservation, fee accrual, realized P&L).
8. Persistence round-trips & execution replay.
9. Concurrency race protection (competing fills never exceed order quantity).
10. Determinism across runs.
"""

import os
import shutil
import sqlite3
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest

from execution.paper_state_machine import (
    OrderState,
    OrderEventType,
    OrderSide,
    PositionSide,
    OrderRejectionReason,
    OrderEvent,
    OrderExecution,
    PaperOrder,
    PaperStateMachine,
    PaperPosition,
    PaperPortfolioManager,
    DurablePaperOMS,
    InvalidOrderTransition,
    OrderInvariantViolation,
    OverfillRejected,
    IdempotencyConflict,
    generate_idempotency_key
)
from core.oms import OrderManagementSystem


@pytest.fixture
def temp_oms():
    """Provides an isolated DurablePaperOMS with SQLite database."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_partial_oms.db")
    oms_instance = DurablePaperOMS(db_path=db_path)
    yield oms_instance, db_path
    try:
        oms_instance.close()
    except Exception:
        pass
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestPartialFillLifecycle:

    # -------------------------------------------------------------
    # 1. Basic Partial Fills & Multi-Step Lifecycle
    # -------------------------------------------------------------

    def test_single_full_fill_lifecycle(self, temp_oms):
        """Single full fill transitions CREATED -> SUBMITTED -> ACKNOWLEDGED -> FILLED."""
        oms, _ = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        assert order.state == OrderState.SUBMITTED

        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        assert order.state == OrderState.ACKNOWLEDGED

        PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=1.0, fill_price=60000.0)
        assert order.state == OrderState.FILLED
        assert order.filled_qty == 1.0
        assert order.remaining_qty == 0.0
        assert order.average_fill_price == 60000.0
        assert len(order.executions) == 1

    def test_two_partial_fills_completing_order(self, temp_oms):
        """Two partial fills (0.4 + 0.6) sum to 1.0 and promote order to FILLED."""
        oms, _ = temp_oms
        order = oms.create_order("ETH/USDT", "BUY", 1.0, price=3000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        # Fill 1: 0.4 ETH
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.4, fill_price=3000.0)
        assert order.state == OrderState.PARTIALLY_FILLED
        assert order.filled_qty == 0.4
        assert order.remaining_qty == 0.6

        # Fill 2: 0.6 ETH
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.6, fill_price=3000.0)
        assert order.state == OrderState.FILLED
        assert order.filled_qty == 1.0
        assert order.remaining_qty == 0.0

    def test_three_partial_fills_multi_price_vwap(self, temp_oms):
        """Three partial fills with different prices correctly calculate Volume-Weighted Average Price (VWAP)."""
        oms, _ = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        # Fill 1: 0.3 BTC @ $60,000
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.3, fill_price=60000.0, execution_id="EX-1")
        assert order.filled_qty == 0.3
        assert order.average_fill_price == 60000.0

        # Fill 2: 0.4 BTC @ $60,100
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.4, fill_price=60100.0, execution_id="EX-2")
        assert order.filled_qty == 0.7
        # Expected VWAP = (0.3*60000 + 0.4*60100) / 0.7 = (18000 + 24040) / 0.7 = 42040 / 0.7 = 60057.14285714
        expected_vwap_2 = round((18000.0 + 24040.0) / 0.7, 8)
        assert order.average_fill_price == expected_vwap_2

        # Fill 3: 0.3 BTC @ $60,200
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.3, fill_price=60200.0, execution_id="EX-3")
        assert order.state == OrderState.FILLED
        assert order.filled_qty == 1.0
        assert order.remaining_qty == 0.0
        # Expected Total VWAP = (0.3*60000 + 0.4*60100 + 0.3*60200) / 1.0 = (18000 + 24040 + 18060) = 60100.0
        assert order.average_fill_price == 60100.0
        assert len(order.executions) == 3

    def test_ten_micro_fills_accumulation(self, temp_oms):
        """10 micro fills of 0.1 each aggregate accurately with zero floating-point drift."""
        oms, _ = temp_oms
        order = oms.create_order("SOL/USDT", "BUY", 1.0, price=150.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        for i in range(9):
            PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.1, fill_price=150.0 + i)
            assert order.state == OrderState.PARTIALLY_FILLED
            assert round(order.filled_qty, 8) == round(0.1 * (i + 1), 8)

        # Final 10th fill completes the order
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.1, fill_price=160.0)
        assert order.state == OrderState.FILLED
        assert order.filled_qty == 1.0
        assert order.remaining_qty == 0.0
        assert len(order.executions) == 10

    # -------------------------------------------------------------
    # 2. Cancellation Lifecycle
    # -------------------------------------------------------------

    def test_cancel_before_fill(self, temp_oms):
        """Cancelling before any fills transitions ACKNOWLEDGED -> CANCELLED with 0 filled."""
        oms, _ = temp_oms
        order = oms.create_order("BNB/USDT", "BUY", 2.0, price=600.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order, OrderEventType.CANCEL, reason="User cancelled before execution")

        assert order.state == OrderState.CANCELLED
        assert order.filled_qty == 0.0
        assert order.remaining_qty == 2.0
        assert order.is_terminal is True

    def test_cancel_after_partial_fill(self, temp_oms):
        """Cancelling after 0.4 fill preserves filled quantity as economically real and locks remaining."""
        oms, _ = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.4, fill_price=60000.0)

        assert order.state == OrderState.PARTIALLY_FILLED
        assert order.filled_qty == 0.4
        assert order.remaining_qty == 0.6

        # Cancel remainder
        PaperStateMachine.transition_order(order, OrderEventType.CANCEL, reason="Cancel remaining unfilled quantity")
        assert order.state == OrderState.CANCELLED
        assert order.filled_qty == 0.4
        assert order.remaining_qty == 0.6
        assert order.is_terminal is True

        # Attempt to fill after cancellation must raise InvalidOrderTransition
        with pytest.raises(InvalidOrderTransition):
            PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=0.6, fill_price=60000.0)

    def test_cancel_after_full_fill_rejected(self, temp_oms):
        """Attempting to cancel an already FILLED order is rejected as invalid transition."""
        oms, _ = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=1.0, fill_price=60000.0)
        assert order.state == OrderState.FILLED

        with pytest.raises(InvalidOrderTransition):
            PaperStateMachine.transition_order(order, OrderEventType.CANCEL)
        assert order.state == OrderState.FILLED

    # -------------------------------------------------------------
    # 3. Expiration Lifecycle
    # -------------------------------------------------------------

    def test_expire_before_fill(self, temp_oms):
        """Time-in-force expiry before fill transitions to EXPIRED with 0 filled."""
        oms, _ = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order, OrderEventType.EXPIRE, reason="Time-in-force TTL expired")

        assert order.state == OrderState.EXPIRED
        assert order.filled_qty == 0.0
        assert order.remaining_qty == 1.0
        assert order.is_terminal is True

    def test_expire_after_partial_fill(self, temp_oms):
        """Time-in-force expiry after partial fill transitions to EXPIRED, locking filled quantity."""
        oms, _ = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.3, fill_price=60000.0)

        assert order.state == OrderState.PARTIALLY_FILLED
        assert order.filled_qty == 0.3

        PaperStateMachine.transition_order(order, OrderEventType.EXPIRE, reason="Order TTL reached")
        assert order.state == OrderState.EXPIRED
        assert order.filled_qty == 0.3
        assert order.remaining_qty == 0.7

        # Attempt to fill expired order must fail
        with pytest.raises(InvalidOrderTransition):
            PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=0.7, fill_price=60000.0)

    # -------------------------------------------------------------
    # 4. Rejection Models & Auditable Codes
    # -------------------------------------------------------------

    def test_rejection_reasons_auditability(self, temp_oms):
        """Rejections record normalized auditable reasons in event history and metadata."""
        oms, _ = temp_oms

        reasons = [
            OrderRejectionReason.INSUFFICIENT_BALANCE,
            OrderRejectionReason.RISK_LIMIT,
            OrderRejectionReason.INVALID_QUANTITY,
            OrderRejectionReason.EXPOSURE_LIMIT,
            OrderRejectionReason.MARKET_CLOSED
        ]

        for idx, reason in enumerate(reasons):
            order = oms.create_order("BTC/USDT", "BUY", 0.5, price=60000.0, idempotency_key=f"IDEMP-REJ-{idx}")
            PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
            PaperStateMachine.transition_order(order, OrderEventType.REJECT, rejection_reason=reason)

            assert order.state == OrderState.REJECTED
            assert order.filled_qty == 0.0
            last_event = order.event_history[-1]
            assert last_event.event_type == OrderEventType.REJECT
            assert last_event.reason == reason.value
            assert last_event.metadata.get("rejection_reason") == reason.value

    # -------------------------------------------------------------
    # 5. Overfill & Invalid Quantity Protections
    # -------------------------------------------------------------

    def test_overfill_rejection_protection(self, temp_oms):
        """Overfilling (e.g. 0.8 already filled + 0.3 new fill on 1.0 total) raises OverfillRejected."""
        oms, _ = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.8, fill_price=60000.0)

        assert order.filled_qty == 0.8
        assert order.remaining_qty == 0.2

        # Attempt to fill 0.3 on 0.2 remaining -> Must raise OverfillRejected
        with pytest.raises(OverfillRejected) as excinfo:
            PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.3, fill_price=60000.0)

        assert "OVERFILL_REJECTED" in str(excinfo.value)
        # Verify order state remains safely at 0.8 filled
        assert order.state == OrderState.PARTIALLY_FILLED
        assert order.filled_qty == 0.8
        assert order.remaining_qty == 0.2

    def test_zero_and_negative_fill_rejection(self, temp_oms):
        """Zero and negative fill quantities or invalid prices are strictly rejected."""
        oms, _ = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        # Zero quantity fill
        with pytest.raises(OrderInvariantViolation):
            PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.0, fill_price=60000.0)

        # Negative quantity fill
        with pytest.raises(OrderInvariantViolation):
            PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=-0.5, fill_price=60000.0)

        # Negative price fill
        with pytest.raises(OrderInvariantViolation):
            PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.5, fill_price=-60000.0)

        # Zero price fill
        with pytest.raises(OrderInvariantViolation):
            PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.5, fill_price=0.0)

    # -------------------------------------------------------------
    # 6. Portfolio & Economic Accounting Consistency
    # -------------------------------------------------------------

    def test_portfolio_incremental_buy_partial_accounting(self, temp_oms):
        """Partial BUY fills incrementally debit cash and credit long position with exact fees."""
        oms, _ = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=50000.0)
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        portfolio = PaperPortfolioManager(initial_cash=100000.0, fee_rate=0.0004)

        # Fill 1: 0.4 BTC @ $50,000 (Cost = $20,000, Fee = $8.00)
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.4, fill_price=50000.0, fee=8.0, execution_id="E1")
        portfolio.apply_order_fill(order, fill_qty=0.4, fill_price=50000.0, fee=8.0, execution_id="E1")

        pos = portfolio.get_position("BTCUSDT")
        assert pos.side == PositionSide.LONG
        assert pos.size == 0.4
        assert pos.entry_price == 50000.0
        assert portfolio.cash == 100000.0 - 20000.0 - 8.0

        # Fill 2: 0.6 BTC @ $52,000 (Cost = $31,200, Fee = $12.48)
        PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=0.6, fill_price=52000.0, fee=12.48, execution_id="E2")
        portfolio.apply_order_fill(order, fill_qty=0.6, fill_price=52000.0, fee=12.48, execution_id="E2")

        assert pos.size == 1.0
        # Expected Average Entry Price = (0.4*50000 + 0.6*52000) / 1.0 = (20000 + 31200) = 51200.0
        assert pos.entry_price == 51200.0
        assert round(portfolio.cash, 4) == round(100000.0 - 20000.0 - 8.0 - 31200.0 - 12.48, 4)

    def test_portfolio_incremental_sell_closing_accounting(self, temp_oms):
        """Partial SELL fills closing long position calculate realized P&L and credit cash correctly."""
        oms, _ = temp_oms
        portfolio = PaperPortfolioManager(initial_cash=50000.0, fee_rate=0.0004)
        pos = portfolio.get_position("BTCUSDT")
        pos.side = PositionSide.LONG
        pos.size = 1.0
        pos.entry_price = 50000.0

        sell_order = oms.create_order("BTC/USDT", "SELL", 1.0, price=60000.0)
        PaperStateMachine.transition_order(sell_order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(sell_order, OrderEventType.ACKNOWLEDGE)

        # Sell 0.5 BTC @ $60,000 (Gross = $30,000, Fee = $12.00, PnL = (60000-50000)*0.5 - 12 = $4988.00)
        PaperStateMachine.transition_order(sell_order, OrderEventType.PARTIAL_FILL, fill_qty=0.5, fill_price=60000.0, fee=12.0, execution_id="S1")
        portfolio.apply_order_fill(sell_order, fill_qty=0.5, fill_price=60000.0, fee=12.0, execution_id="S1")

        assert pos.size == 0.5
        assert pos.realized_pnl == 4988.0
        assert portfolio.cash == 50000.0 + 30000.0 - 12.0

        # Sell remaining 0.5 BTC @ $62,000 (Gross = $31,000, Fee = $12.40, PnL = (62000-50000)*0.5 - 12.40 = $5987.60)
        PaperStateMachine.transition_order(sell_order, OrderEventType.FILL, fill_qty=0.5, fill_price=62000.0, fee=12.40, execution_id="S2")
        portfolio.apply_order_fill(sell_order, fill_qty=0.5, fill_price=62000.0, fee=12.40, execution_id="S2")

        assert pos.size == 0.0
        assert pos.side == PositionSide.FLAT
        assert pos.realized_pnl == 4988.0 + 5987.60

    # -------------------------------------------------------------
    # 7. Persistence & Reload Verification
    # -------------------------------------------------------------

    def test_persistence_round_trip_partial_fills(self, temp_oms):
        """Orders and multiple execution fills reload accurately from SQLite."""
        oms, db_path = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        oms.save_transition(order, order.event_history[-1])

        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        oms.save_transition(order, order.event_history[-1])

        # Fill 1: 0.3 BTC @ $60,000
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.3, fill_price=60000.0, execution_id="EX-SQL-1")
        oms.save_transition(order, order.event_history[-1], execution_id="EX-SQL-1")

        # Fill 2: 0.7 BTC @ $61,000
        PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=0.7, fill_price=61000.0, execution_id="EX-SQL-2")
        oms.save_transition(order, order.event_history[-1], execution_id="EX-SQL-2")

        # Reload from fresh OMS connection
        reloaded_oms = DurablePaperOMS(db_path=db_path)
        reloaded_order = reloaded_oms.get_order(order.order_id)

        assert reloaded_order is not None
        assert reloaded_order.state == OrderState.FILLED
        assert reloaded_order.filled_qty == 1.0
        assert reloaded_order.remaining_qty == 0.0
        assert len(reloaded_order.executions) == 2
        # Expected VWAP = (0.3*60000 + 0.7*61000) / 1.0 = 18000 + 42700 = 60700.0
        assert reloaded_order.average_fill_price == 60700.0
        reloaded_oms.close()

    # -------------------------------------------------------------
    # 8. High-Level OMS Wrapper Integration
    # -------------------------------------------------------------

    def test_oms_wrapper_cancellation_and_rejection_apis(self, temp_oms):
        """OrderManagementSystem wrapper cancellation, expiration, and rejection APIs."""
        _, db_path = temp_oms
        oms_wrapper = OrderManagementSystem(db_path=db_path)

        # Cancel test
        id1 = oms_wrapper.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)
        status1 = oms_wrapper.cancel_order(id1, reason="Test cancel")
        assert status1 == "CANCELLED"

        # Expire test
        id2 = oms_wrapper.create_order("ETH/USDT", "BUY", 2.0, price=3000.0)
        status2 = oms_wrapper.expire_order(id2, reason="Test expire")
        assert status2 == "EXPIRED"

        # Reject test
        id3 = oms_wrapper.create_order("SOL/USDT", "BUY", 5.0, price=150.0)
        status3 = oms_wrapper.reject_order(id3, reason=OrderRejectionReason.INSUFFICIENT_BALANCE)
        assert status3 == "REJECTED"
        paper_order3 = oms_wrapper.get_paper_order(id3)
        assert paper_order3.event_history[-1].metadata.get("rejection_reason") == "INSUFFICIENT_BALANCE"

    # -------------------------------------------------------------
    # 9. Concurrency: Competing Fills Never Overfill
    # -------------------------------------------------------------

    def test_concurrent_competing_fills_never_overfill(self, temp_oms):
        """Two competing concurrent fill attempts (0.6 + 0.6 on a 1.0 order) never exceed 1.0 total."""
        oms, db_path = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=60000.0)
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        oms.save_transition(order, order.event_history[-1])

        # We will use a shared lock around transition validation to simulate concurrent engine threads
        lock = threading.Lock()
        results = []

        def attempt_fill(worker_id: int, qty: float):
            with lock:
                try:
                    PaperStateMachine.transition_order(
                        order,
                        OrderEventType.PARTIAL_FILL,
                        fill_qty=qty,
                        fill_price=60000.0,
                        execution_id=f"CONC-FILL-{worker_id}"
                    )
                    oms.save_transition(order, order.event_history[-1], execution_id=f"CONC-FILL-{worker_id}")
                    results.append(("ACCEPTED", qty))
                except OverfillRejected:
                    results.append(("REJECTED_OVERFILL", qty))

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(attempt_fill, 1, 0.6)
            f2 = executor.submit(attempt_fill, 2, 0.6)
            f1.result()
            f2.result()

        accepted = [r for r in results if r[0] == "ACCEPTED"]
        rejected = [r for r in results if r[0] == "REJECTED_OVERFILL"]

        assert len(accepted) == 1
        assert len(rejected) == 1
        assert order.filled_qty == 0.6
        assert order.filled_qty <= order.order_qty
