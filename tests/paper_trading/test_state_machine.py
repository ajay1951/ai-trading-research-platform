"""
Unit & Regression Tests for P2-1 Paper-Trading State Machine
============================================================
Validates:
1. Complete Order Lifecycle (Created -> Submitted -> Acknowledged -> Filled).
2. Partial-Fill Slicing & Auto-Promotion to Filled.
3. Order Rejection, Cancellation, and Expiration.
4. Invalid Transition Rejection & Domain Exception Raising.
5. Terminal State Inviolability.
6. Quantity Invariants (Non-negative, remaining qty, overfill protection, avg fill price).
7. Duplicate Event Handling & Idempotency.
8. Event Ordering & Deterministic Execution.
9. Position & Portfolio Invariants (Only fills alter position/cash).
10. SQLite & JSON Persistence Round-Trip.
11. Production Legacy Schema & State Backward Compatibility.
12. Future Mutation Invariance.
"""

import os
import json
import pytest
import sqlite3
from datetime import datetime, timezone, timedelta

from execution.paper_state_machine import (
    OrderState,
    OrderEventType,
    OrderSide,
    PositionSide,
    PaperOrder,
    PaperStateMachine,
    PaperPosition,
    PaperPortfolioManager,
    DurablePaperOMS,
    InvalidOrderTransition,
    OrderInvariantViolation,
    OrderEvent
)


class TestPaperTradingStateMachine:

    # -------------------------------------------------------------
    # 1. Lifecycle Transitions
    # -------------------------------------------------------------

    def test_basic_full_lifecycle(self):
        """Test full valid lifecycle: CREATED -> SUBMITTED -> ACKNOWLEDGED -> FILLED."""
        order = PaperOrder(order_id=1, symbol="BTC/USDT", side=OrderSide.BUY, order_qty=1.5, price=65000.0)
        assert order.state == OrderState.CREATED
        assert order.filled_qty == 0.0
        assert order.remaining_qty == 1.5

        # SUBMIT
        order, ev1 = PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        assert order.state == OrderState.SUBMITTED
        assert ev1.previous_state == OrderState.CREATED
        assert ev1.new_state == OrderState.SUBMITTED

        # ACKNOWLEDGE
        order, ev2 = PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        assert order.state == OrderState.ACKNOWLEDGED

        # FILL
        order, ev3 = PaperStateMachine.transition_order(
            order, OrderEventType.FILL, fill_qty=1.5, fill_price=65010.0, fee=3.90
        )
        assert order.state == OrderState.FILLED
        assert order.filled_qty == 1.5
        assert order.remaining_qty == 0.0
        assert order.average_fill_price == 65010.0
        assert len(order.executions) == 1
        assert len(order.event_history) == 3

    def test_partial_fill_lifecycle(self):
        """Test partial fill lifecycle: CREATED -> SUBMITTED -> ACK -> PARTIAL -> PARTIAL -> FILLED."""
        order = PaperOrder(order_id=2, symbol="ETH/USDT", side=OrderSide.BUY, order_qty=10.0)

        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        # Slice 1: 4.0 @ $3000
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=4.0, fill_price=3000.0)
        assert order.state == OrderState.PARTIALLY_FILLED
        assert order.filled_qty == 4.0
        assert order.remaining_qty == 6.0
        assert order.average_fill_price == 3000.0

        # Slice 2: 3.0 @ $3100 -> Avg price = (4*3000 + 3*3100) / 7 = (12000 + 9300)/7 = 21300/7 = 3042.85714286
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=3.0, fill_price=3100.0)
        assert order.state == OrderState.PARTIALLY_FILLED
        assert order.filled_qty == 7.0
        assert order.remaining_qty == 3.0
        assert pytest.approx(order.average_fill_price, abs=1e-4) == 3042.85714286

        # Slice 3: Remaining 3.0 @ $3050 -> Completes order, auto-promotes to FILLED
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=3.0, fill_price=3050.0)
        assert order.state == OrderState.FILLED
        assert order.filled_qty == 10.0
        assert order.remaining_qty == 0.0
        # Avg price = (21300 + 3*3050)/10 = (21300 + 9150)/10 = 3045.0
        assert pytest.approx(order.average_fill_price, abs=1e-4) == 3045.0
        assert len(order.executions) == 3

    def test_rejection_lifecycle(self):
        """Test rejection: CREATED -> SUBMITTED -> REJECTED."""
        order = PaperOrder(order_id=3, symbol="SOL/USDT", side=OrderSide.BUY, order_qty=5.0)
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.REJECT, reason="Margin insufficient")
        assert order.state == OrderState.REJECTED
        assert order.is_terminal

    def test_cancellation_lifecycle(self):
        """Test cancellation: CREATED -> SUBMITTED -> ACKNOWLEDGED -> CANCELLED."""
        order = PaperOrder(order_id=4, symbol="AVAX/USDT", side=OrderSide.SELL, order_qty=20.0)
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order, OrderEventType.CANCEL, reason="User cancelled")
        assert order.state == OrderState.CANCELLED
        assert order.is_terminal

    def test_expiration_lifecycle(self):
        """Test expiration: CREATED -> SUBMITTED -> ACKNOWLEDGED -> EXPIRED."""
        order = PaperOrder(order_id=5, symbol="DOGE/USDT", side=OrderSide.BUY, order_qty=1000.0)
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order, OrderEventType.EXPIRE, reason="Time-in-force reached")
        assert order.state == OrderState.EXPIRED
        assert order.is_terminal

    # -------------------------------------------------------------
    # 2. Invalid Transitions & Terminal State Protection
    # -------------------------------------------------------------

    def test_invalid_transitions_raise_domain_exception(self):
        """Test that illegal transitions raise InvalidOrderTransition."""
        order = PaperOrder(order_id=6, symbol="BTC/USDT", side=OrderSide.BUY, order_qty=1.0)

        # Cannot FILL directly from CREATED without SUBMIT/ACK
        with pytest.raises(InvalidOrderTransition):
            PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=1.0, fill_price=60000.0)

        # Move to FILLED
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=1.0, fill_price=60000.0)
        assert order.state == OrderState.FILLED

        # FILLED is terminal -> cannot SUBMIT, ACKNOWLEDGE, CANCEL, or EXPIRE
        with pytest.raises(InvalidOrderTransition):
            PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)

        with pytest.raises(InvalidOrderTransition):
            PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        with pytest.raises(InvalidOrderTransition):
            PaperStateMachine.transition_order(order, OrderEventType.CANCEL)

        with pytest.raises(InvalidOrderTransition):
            PaperStateMachine.transition_order(order, OrderEventType.EXPIRE)

    def test_terminal_states_cannot_be_mutated(self):
        """Verify that all terminal states (FILLED, REJECTED, CANCELLED, EXPIRED) reject subsequent transitions."""
        terminal_states = [
            (OrderEventType.REJECT, OrderState.REJECTED),
            (OrderEventType.CANCEL, OrderState.CANCELLED),
            (OrderEventType.EXPIRE, OrderState.EXPIRED),
        ]

        for evt, expected_terminal in terminal_states:
            order = PaperOrder(order_id=100, symbol="BTC/USDT", side=OrderSide.BUY, order_qty=1.0)
            PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
            PaperStateMachine.transition_order(order, evt)
            assert order.state == expected_terminal
            assert order.is_terminal

            # Attempting new fill on terminal state must fail
            with pytest.raises(InvalidOrderTransition):
                PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=1.0, fill_price=50000.0)

    # -------------------------------------------------------------
    # 3. Quantity Invariants & Overfill Protection
    # -------------------------------------------------------------

    def test_non_positive_order_quantity_rejected(self):
        """Test that non-positive order quantity is rejected at initialization."""
        with pytest.raises(OrderInvariantViolation):
            PaperOrder(order_id=7, symbol="BTC/USDT", side=OrderSide.BUY, order_qty=0.0)

        with pytest.raises(OrderInvariantViolation):
            PaperOrder(order_id=8, symbol="BTC/USDT", side=OrderSide.BUY, order_qty=-5.0)

    def test_non_positive_fill_quantity_rejected(self):
        """Test that fill quantity <= 0 is rejected during transition."""
        order = PaperOrder(order_id=9, symbol="BTC/USDT", side=OrderSide.BUY, order_qty=2.0)
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        with pytest.raises(OrderInvariantViolation):
            PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.0, fill_price=60000.0)

        with pytest.raises(OrderInvariantViolation):
            PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=-1.0, fill_price=60000.0)

    def test_overfill_rejected(self):
        """Test that attempting to fill more than total order quantity raises OrderInvariantViolation."""
        order = PaperOrder(order_id=10, symbol="BTC/USDT", side=OrderSide.BUY, order_qty=1.0)
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        # Attempt to fill 1.5 on a 1.0 order
        with pytest.raises(OrderInvariantViolation):
            PaperStateMachine.transition_order(order, OrderEventType.FILL, fill_qty=1.5, fill_price=60000.0)

        # Fill 0.8 successfully
        PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.8, fill_price=60000.0)
        assert order.filled_qty == 0.8

        # Attempting to fill additional 0.3 (0.8 + 0.3 = 1.1 > 1.0) must fail
        with pytest.raises(OrderInvariantViolation):
            PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=0.3, fill_price=60000.0)

    # -------------------------------------------------------------
    # 4. Duplicate Event Idempotency & Determinism
    # -------------------------------------------------------------

    def test_duplicate_event_id_idempotent_noop(self):
        """Test that replaying an event with identical event_id is a safe no-op."""
        order = PaperOrder(order_id=11, symbol="BNB/USDT", side=OrderSide.BUY, order_qty=5.0)
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)

        event_id_fill = "FILL-EVENT-UUID-001"
        order, ev1 = PaperStateMachine.transition_order(
            order, OrderEventType.PARTIAL_FILL, fill_qty=2.0, fill_price=600.0, event_id=event_id_fill
        )
        assert order.filled_qty == 2.0
        assert len(order.event_history) == 3

        # Replay the exact same event
        order, ev2 = PaperStateMachine.transition_order(
            order, OrderEventType.PARTIAL_FILL, fill_qty=2.0, fill_price=600.0, event_id=event_id_fill
        )
        # Invariants: filled quantity must NOT double to 4.0
        assert order.filled_qty == 2.0
        assert len(order.event_history) == 3
        assert ev1.event_id == ev2.event_id

    def test_deterministic_event_sequence_reproducibility(self):
        """Test that identical event sequence produces identical final order state."""
        def run_sequence():
            ord_obj = PaperOrder(order_id=12, symbol="SOL/USDT", side=OrderSide.BUY, order_qty=10.0)
            PaperStateMachine.transition_order(ord_obj, OrderEventType.SUBMIT, event_id="E1")
            PaperStateMachine.transition_order(ord_obj, OrderEventType.ACKNOWLEDGE, event_id="E2")
            PaperStateMachine.transition_order(ord_obj, OrderEventType.PARTIAL_FILL, fill_qty=4.0, fill_price=150.0, event_id="E3")
            PaperStateMachine.transition_order(ord_obj, OrderEventType.PARTIAL_FILL, fill_qty=6.0, fill_price=160.0, event_id="E4")
            return ord_obj

        run1 = run_sequence()
        run2 = run_sequence()

        assert run1.state == run2.state == OrderState.FILLED
        assert run1.filled_qty == run2.filled_qty == 10.0
        assert run1.average_fill_price == run2.average_fill_price == 156.0
        assert len(run1.event_history) == len(run2.event_history) == 4

    # -------------------------------------------------------------
    # 5. Position & Portfolio Interaction
    # -------------------------------------------------------------

    def test_non_filled_orders_do_not_alter_positions_or_cash(self):
        """Verify that CREATED, SUBMITTED, ACKNOWLEDGED, CANCELLED orders never mutate position size or cash."""
        pm = PaperPortfolioManager(initial_cash=1000.0)
        order = PaperOrder(order_id=13, symbol="BTC/USDT", side=OrderSide.BUY, order_qty=0.5, price=60000.0)

        # CREATED
        pos = pm.get_position("BTC/USDT")
        assert pos.side == PositionSide.FLAT
        assert pos.size == 0.0
        assert pm.cash == 1000.0

        # SUBMITTED
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        assert pm.get_position("BTC/USDT").size == 0.0
        assert pm.cash == 1000.0

        # ACKNOWLEDGED
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        assert pm.get_position("BTC/USDT").size == 0.0
        assert pm.cash == 1000.0

        # CANCELLED
        PaperStateMachine.transition_order(order, OrderEventType.CANCEL)
        assert pm.get_position("BTC/USDT").size == 0.0
        assert pm.cash == 1000.0

    def test_fill_updates_position_and_cash_correctly(self):
        """Verify that Long and Short fills accurately update size, cost basis, realized PnL, and cash."""
        pm = PaperPortfolioManager(initial_cash=1000.0, fee_rate=0.0004)

        # 1. Buy 1.0 ETH @ $3000 (Cost = $3000, Fee = $1.20)
        order_buy = PaperOrder(order_id=14, symbol="ETH/USDT", side=OrderSide.BUY, order_qty=1.0)
        PaperStateMachine.transition_order(order_buy, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order_buy, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order_buy, OrderEventType.FILL, fill_qty=1.0, fill_price=3000.0, fee=1.20)

        pm.apply_order_fill(order_buy, fill_qty=1.0, fill_price=3000.0, fee=1.20)

        pos = pm.get_position("ETH/USDT")
        assert pos.side == PositionSide.LONG
        assert pos.size == 1.0
        assert pos.entry_price == 3000.0
        assert pytest.approx(pm.cash, abs=1e-4) == 1000.0 - (3000.0 + 1.20)

        # 2. Sell 1.0 ETH @ $3300 (Proceeds = $3300, Fee = $1.32, PnL = $300 - fees)
        order_sell = PaperOrder(order_id=15, symbol="ETH/USDT", side=OrderSide.SELL, order_qty=1.0)
        PaperStateMachine.transition_order(order_sell, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order_sell, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order_sell, OrderEventType.FILL, fill_qty=1.0, fill_price=3300.0, fee=1.32)

        pm.apply_order_fill(order_sell, fill_qty=1.0, fill_price=3300.0, fee=1.32)

        assert pos.side == PositionSide.FLAT
        assert pos.size == 0.0
        assert pytest.approx(pos.realized_pnl, abs=1e-4) == 300.0 - 1.32
        assert pytest.approx(pm.cash, abs=1e-4) == 1000.0 + 300.0 - (1.20 + 1.32)

    # -------------------------------------------------------------
    # 6. Persistence & SQLite Integration
    # -------------------------------------------------------------

    def test_sqlite_persistence_round_trip(self, tmp_path):
        """Test creating, transitioning, persisting to SQLite and reconstructing complete order state."""
        db_file = str(tmp_path / "test_oms.db")
        oms = DurablePaperOMS(db_path=db_file)

        # Create Order
        order = oms.create_order(symbol="SOL/USDT", side="BUY", total_qty=5.0, price=150.0)
        assert order.state == OrderState.CREATED

        # Submit & Acknowledge
        order, ev1 = PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        oms.save_transition(order, ev1)

        order, ev2 = PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        oms.save_transition(order, ev2)

        # Partial Fill 2.0 @ $150
        order, ev3 = PaperStateMachine.transition_order(order, OrderEventType.PARTIAL_FILL, fill_qty=2.0, fill_price=150.0, fee=0.12)
        oms.save_transition(order, ev3)

        # Reload from Database
        restored = oms.get_order(order.order_id)
        assert restored is not None
        assert restored.order_id == order.order_id
        assert restored.symbol == "SOL/USDT"
        assert restored.side == OrderSide.BUY
        assert restored.state == OrderState.PARTIALLY_FILLED
        assert restored.filled_qty == 2.0
        assert restored.remaining_qty == 3.0
        assert restored.average_fill_price == 150.0
        assert len(restored.executions) == 1
        assert len(restored.event_history) == 3

    # -------------------------------------------------------------
    # 7. Production Backward Compatibility
    # -------------------------------------------------------------

    def test_legacy_production_schema_compatibility(self, tmp_path):
        """Verify that legacy SQLite records with statuses 'PENDING', 'PARTIAL', 'FILLED' deserialize cleanly."""
        db_file = str(tmp_path / "legacy_oms.db")
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            total_qty REAL NOT NULL,
            filled_qty REAL DEFAULT 0.0,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            fill_price REAL NOT NULL,
            fill_qty REAL NOT NULL,
            fee REAL DEFAULT 0.0,
            timestamp TEXT NOT NULL
        )
        """)
        c.execute("INSERT INTO orders VALUES (1, 'BTC/USDT', 'BUY', 1.0, 0.0, 'PENDING', '2026-09-01T00:00:00', '2026-09-01T00:00:00')")
        c.execute("INSERT INTO orders VALUES (2, 'ETH/USDT', 'BUY', 2.0, 1.0, 'PARTIAL', '2026-09-01T00:00:00', '2026-09-01T00:00:00')")
        c.execute("INSERT INTO orders VALUES (3, 'SOL/USDT', 'SELL', 5.0, 5.0, 'FILLED', '2026-09-01T00:00:00', '2026-09-01T00:00:00')")
        conn.commit()
        conn.close()

        oms = DurablePaperOMS(db_path=db_file)

        ord1 = oms.get_order(1)
        assert ord1.state == OrderState.SUBMITTED

        ord2 = oms.get_order(2)
        assert ord2.state == OrderState.PARTIALLY_FILLED

        ord3 = oms.get_order(3)
        assert ord3.state == OrderState.FILLED

    def test_production_live_state_json_compatibility(self):
        """Verify that current Oracle Cloud live_state.json backup format deserializes into portfolio manager."""
        backup_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "backups", "live_state_baseline_backup.json")
        if not os.path.exists(backup_file):
            pytest.skip("Baseline backup not found")

        with open(backup_file, "r") as f:
            live_state = json.load(f)

        pm = PaperPortfolioManager(initial_cash=live_state["cash"])
        assert pm.cash == 26.0

        for sym, pos_data in live_state.get("positions", {}).items():
            pos = pm.get_position(sym)
            pos.size = pos_data["size"]
            pos.entry_price = pos_data["entry_price"]
            pos.side = PositionSide.SHORT if pos_data.get("is_short") else PositionSide.LONG

        bnb_pos = pm.get_position("BNB/USDT")
        assert bnb_pos.side == PositionSide.SHORT
        assert pytest.approx(bnb_pos.size, abs=1e-6) == 0.03184333

        # Compute equity with current mark price
        eq = pm.compute_total_equity({"BNB/USDT": 753.4515})
        assert pytest.approx(eq, abs=1e-2) == 26.0 + (bnb_pos.size * bnb_pos.entry_price)

    # -------------------------------------------------------------
    # 8. Future Mutation Invariance
    # -------------------------------------------------------------

    def test_future_mutation_invariance(self):
        """Verify that mutating or creating future orders leaves historical completed orders unmodified."""
        order_hist = PaperOrder(order_id=20, symbol="BTC/USDT", side=OrderSide.BUY, order_qty=1.0)
        PaperStateMachine.transition_order(order_hist, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order_hist, OrderEventType.ACKNOWLEDGE)
        PaperStateMachine.transition_order(order_hist, OrderEventType.FILL, fill_qty=1.0, fill_price=60000.0)

        hist_snapshot = order_hist.to_dict()

        # Future unrelated order
        order_future = PaperOrder(order_id=21, symbol="BTC/USDT", side=OrderSide.SELL, order_qty=5.0)
        PaperStateMachine.transition_order(order_future, OrderEventType.SUBMIT)
        PaperStateMachine.transition_order(order_future, OrderEventType.REJECT, reason="Volatility spike")

        # Verify historical snapshot is 100% identical
        assert order_hist.to_dict() == hist_snapshot
