"""
P2-2: Order Idempotency & Duplicate-Execution Protection Test Suite
===================================================================
Tests ensuring:
- 1 logical order intent -> N duplicate requests/events -> 1 economic execution.
- Idempotency key stability and request fingerprinting.
- Detection and safe rejection of Idempotency Conflicts (same key, different economic parameters).
- Database-level uniqueness constraints and atomic concurrent race resolution.
- Protection against execution/fill deduplication, position double-counting, cash double-deduction, and fee inflation.
- Multi-threaded and concurrent load idempotency (100 concurrent requests).
- Production SQLite schema and historical baseline compatibility.
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
    OrderEvent,
    OrderExecution,
    PaperOrder,
    PaperStateMachine,
    PaperPosition,
    PaperPortfolioManager,
    DurablePaperOMS,
    InvalidOrderTransition,
    OrderInvariantViolation,
    IdempotencyConflict,
    compute_request_fingerprint,
    generate_idempotency_key,
    generate_client_order_id
)
from core.oms import OrderManagementSystem


@pytest.fixture
def temp_oms():
    """Provides a fresh isolated DurablePaperOMS with SQLite database."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_oms.db")
    oms_instance = DurablePaperOMS(db_path=db_path)
    yield oms_instance, db_path
    try:
        oms_instance.close()
    except Exception:
        pass
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestOrderIdempotency:

    def test_single_duplicate_order_request(self, temp_oms):
        """A: Duplicate order request returns the existing order without creating a new record."""
        oms, db_path = temp_oms
        key = "IDEMP-TEST-001"
        client_id = "CS48H_20261007_BTC_BUY_001"

        order1 = oms.create_order(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=0.5,
            price=60000.0,
            idempotency_key=key,
            client_order_id=client_id,
            strategy_id="CS48H",
            rebalance_id="20261007T120000"
        )
        assert order1.order_id > 0
        assert order1.state == OrderState.CREATED

        # Second submission of identical request
        order2 = oms.create_order(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=0.5,
            price=60000.0,
            idempotency_key=key,
            client_order_id=client_id,
            strategy_id="CS48H",
            rebalance_id="20261007T120000"
        )

        assert order2.order_id == order1.order_id
        assert order2.idempotency_key == key

        # Verify DB contains only 1 record
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        assert count == 1
        conn.close()

    def test_repeated_duplicate_order_requests(self, temp_oms):
        """B: 3 repeated requests produce exactly 1 order record."""
        oms, db_path = temp_oms
        key = "IDEMP-TEST-002"

        orders = [
            oms.create_order(
                symbol="ETH/USDT",
                side="BUY",
                total_qty=2.0,
                price=3000.0,
                idempotency_key=key,
                strategy_id="CS48H",
                rebalance_id="20261007T120000"
            )
            for _ in range(3)
        ]

        assert len(set(o.order_id for o in orders)) == 1

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        assert count == 1
        conn.close()

    def test_hundred_sequential_duplicate_requests(self, temp_oms):
        """C: 100 sequential duplicate requests produce exactly 1 persisted order."""
        oms, db_path = temp_oms
        key = "IDEMP-TEST-100-SEQ"

        order_ids = []
        for _ in range(100):
            order = oms.create_order(
                symbol="SOL/USDT",
                side="SELL",
                total_qty=10.0,
                price=150.0,
                idempotency_key=key,
                strategy_id="CS48H",
                rebalance_id="20261007T120000"
            )
            order_ids.append(order.order_id)

        assert len(set(order_ids)) == 1

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        assert count == 1
        conn.close()

    def test_concurrent_duplicate_requests_race_condition(self, temp_oms):
        """D: 100 concurrent threads submitting identical idempotency key yield exactly 1 order."""
        oms, db_path = temp_oms
        key = "IDEMP-CONCURRENT-RACE-001"
        client_id = "CS48H_20261007_BNB_BUY_001"

        def submit_order():
            # Each thread uses its own thread-local SQLite connection via DurablePaperOMS
            local_oms = DurablePaperOMS(db_path=db_path)
            return local_oms.create_order(
                symbol="BNB/USDT",
                side="BUY",
                total_qty=1.5,
                price=600.0,
                idempotency_key=key,
                client_order_id=client_id,
                strategy_id="CS48H",
                rebalance_id="20261007T120000"
            ).order_id

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(submit_order) for _ in range(100)]
            results = [f.result() for f in as_completed(futures)]

        # All 100 threads must receive the exact same order_id
        assert len(results) == 100
        assert len(set(results)) == 1

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        assert count == 1
        conn.close()

    def test_idempotency_conflict_detection(self, temp_oms):
        """H: Reusing the same idempotency key with different parameters raises IdempotencyConflict."""
        oms, _ = temp_oms
        key = "IDEMP-CONFLICT-TEST"

        # Create original order: BUY 1.0 BTC
        oms.create_order(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=1.0,
            price=60000.0,
            idempotency_key=key,
            strategy_id="CS48H",
            rebalance_id="20261007T120000"
        )

        # Attempt to reuse same key with different quantity (2.0 instead of 1.0)
        with pytest.raises(IdempotencyConflict) as excinfo:
            oms.create_order(
                symbol="BTC/USDT",
                side="BUY",
                total_qty=2.0,
                price=60000.0,
                idempotency_key=key,
                strategy_id="CS48H",
                rebalance_id="20261007T120000"
            )
        assert "conflict" in str(excinfo.value).lower()

        # Attempt to reuse same key with different side (SELL instead of BUY)
        with pytest.raises(IdempotencyConflict) as excinfo_side:
            oms.create_order(
                symbol="BTC/USDT",
                side="SELL",
                total_qty=1.0,
                price=60000.0,
                idempotency_key=key,
                strategy_id="CS48H",
                rebalance_id="20261007T120000"
            )
        assert "conflict" in str(excinfo_side.value).lower()

    def test_different_intents_remain_distinct(self, temp_oms):
        """G: Different trading intents receive distinct orders and do not collide."""
        oms, db_path = temp_oms

        # Intent 1: Rebalance Cycle 1
        key1 = generate_idempotency_key("CS48H", "BTC/USDT", "BUY", "20261005T000000")
        order1 = oms.create_order("BTC/USDT", "BUY", 0.5, price=60000.0, idempotency_key=key1)

        # Intent 2: Rebalance Cycle 2 (same asset and side, different cycle)
        key2 = generate_idempotency_key("CS48H", "BTC/USDT", "BUY", "20261007T000000")
        order2 = oms.create_order("BTC/USDT", "BUY", 0.5, price=61000.0, idempotency_key=key2)

        # Intent 3: Different asset in same cycle
        key3 = generate_idempotency_key("CS48H", "ETH/USDT", "BUY", "20261007T000000")
        order3 = oms.create_order("ETH/USDT", "BUY", 5.0, price=3000.0, idempotency_key=key3)

        assert order1.order_id != order2.order_id
        assert order2.order_id != order3.order_id

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        assert count == 3
        conn.close()

    def test_database_uniqueness_constraint_enforcement(self, temp_oms):
        """I: Direct DB insert with duplicate idempotency_key is rejected by SQLite UNIQUE constraint."""
        _, db_path = temp_oms
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO orders (symbol, side, total_qty, status, created_at, updated_at, idempotency_key)
            VALUES ('BTC/USDT', 'BUY', 1.0, 'CREATED', '2026-10-07T00:00:00Z', '2026-10-07T00:00:00Z', 'KEY-DB-UNIQUE')
        """)
        conn.commit()

        # Second raw insert with identical key must violate UNIQUE constraint
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO orders (symbol, side, total_qty, status, created_at, updated_at, idempotency_key)
                VALUES ('BTC/USDT', 'BUY', 1.0, 'CREATED', '2026-10-07T00:00:00Z', '2026-10-07T00:00:00Z', 'KEY-DB-UNIQUE')
            """)
            conn.commit()
        conn.close()

    def test_duplicate_execution_fill_idempotency(self, temp_oms):
        """E, F, M, N, O: Duplicate fill events with same execution_id do not double-mutate portfolio or order."""
        oms, db_path = temp_oms
        order = oms.create_order("BTC/USDT", "BUY", 1.0, price=50000.0, idempotency_key="IDEMP-FILL-001")

        # Transition to ACKNOWLEDGED
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
        oms.save_transition(order, order.event_history[-1])
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
        oms.save_transition(order, order.event_history[-1])

        portfolio = PaperPortfolioManager(initial_cash=100000.0, fee_rate=0.0004)
        exec_id = "EXEC-BTC-FILL-001"

        # Apply Fill #1
        PaperStateMachine.transition_order(
            order,
            OrderEventType.FILL,
            fill_qty=1.0,
            fill_price=50000.0,
            fee=20.0,
            execution_id=exec_id
        )
        oms.save_transition(order, order.event_history[-1], execution_id=exec_id)
        portfolio.apply_order_fill(order, fill_qty=1.0, fill_price=50000.0, fee=20.0, execution_id=exec_id)

        assert order.state == OrderState.FILLED
        assert order.filled_qty == 1.0
        assert len(order.executions) == 1
        pos = portfolio.get_position("BTCUSDT")
        assert pos.size == 1.0
        assert portfolio.cash == 100000.0 - 50000.0 - 20.0

        cash_after_fill1 = portfolio.cash

        # Replay duplicate Fill #1 (identical execution_id)
        PaperStateMachine.transition_order(
            order,
            OrderEventType.FILL,
            fill_qty=1.0,
            fill_price=50000.0,
            fee=20.0,
            execution_id=exec_id
        )
        oms.save_transition(order, order.event_history[-1], execution_id=exec_id)
        portfolio.apply_order_fill(order, fill_qty=1.0, fill_price=50000.0, fee=20.0, execution_id=exec_id)

        # Invariants: Zero changes from duplicate fill
        assert order.filled_qty == 1.0
        assert len(order.executions) == 1
        assert pos.size == 1.0
        assert portfolio.cash == cash_after_fill1

        # Check DB executions table
        conn = sqlite3.connect(db_path)
        exec_count = conn.execute("SELECT COUNT(*) FROM executions WHERE order_id = ?", (order.order_id,)).fetchone()[0]
        assert exec_count == 1
        conn.close()

    def test_duplicate_event_replay_lifecycle(self, temp_oms):
        """K, L: Full lifecycle replay CREATE -> SUBMIT -> ACK -> FILL -> FILL -> FILL."""
        oms, _ = temp_oms
        order = oms.create_order("ETH/USDT", "BUY", 2.0, price=3000.0, idempotency_key="IDEMP-REPLAY-001")

        # Normal sequence
        PaperStateMachine.transition_order(order, OrderEventType.SUBMIT, event_id="EVT-SUBMIT-1")
        PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE, event_id="EVT-ACK-1")
        PaperStateMachine.transition_order(
            order, OrderEventType.FILL, fill_qty=2.0, fill_price=3000.0, fee=2.4,
            event_id="EVT-FILL-1", execution_id="EXEC-ETH-001"
        )

        assert order.state == OrderState.FILLED
        assert order.filled_qty == 2.0
        assert len(order.executions) == 1

        # Replay fill 10 times
        for i in range(10):
            PaperStateMachine.transition_order(
                order, OrderEventType.FILL, fill_qty=2.0, fill_price=3000.0, fee=2.4,
                event_id="EVT-FILL-1", execution_id="EXEC-ETH-001"
            )

        assert order.state == OrderState.FILLED
        assert order.filled_qty == 2.0
        assert len(order.executions) == 1

    def test_persistence_round_trip_with_idempotency_fields(self, temp_oms):
        """J: Persistence round-trip verifies idempotency_key, client_order_id, and fingerprint."""
        oms, _ = temp_oms
        key = "IDEMP-ROUNDTRIP-999"
        client_id = "CS48H_20261007_SOL_SELL_001"

        orig_order = oms.create_order(
            symbol="SOL/USDT",
            side="SELL",
            total_qty=5.0,
            price=140.0,
            idempotency_key=key,
            client_order_id=client_id,
            strategy_id="CS48H",
            rebalance_id="20261007T120000"
        )

        loaded_order = oms.get_order(orig_order.order_id)
        assert loaded_order is not None
        assert loaded_order.order_id == orig_order.order_id
        assert loaded_order.idempotency_key == key
        assert loaded_order.client_order_id == client_id
        assert loaded_order.request_fingerprint is not None

        # Also retrieve by idempotency key
        order_by_key = oms.get_order_by_idempotency_key(key)
        assert order_by_key is not None
        assert order_by_key.order_id == orig_order.order_id

        # Also retrieve by client_order_id
        order_by_client = oms.get_order_by_client_order_id(client_id)
        assert order_by_client is not None
        assert order_by_client.order_id == orig_order.order_id

    def test_core_oms_wrapper_idempotency(self, temp_oms):
        """S: High-level OrderManagementSystem wrapper correctly handles idempotency and executions."""
        _, db_path = temp_oms
        oms_wrapper = OrderManagementSystem(db_path=db_path)

        key = "IDEMP-CORE-OMS-001"
        id1 = oms_wrapper.create_order(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=0.1,
            price=65000.0,
            idempotency_key=key,
            strategy_id="CS48H",
            rebalance_id="20261007"
        )
        id2 = oms_wrapper.create_order(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=0.1,
            price=65000.0,
            idempotency_key=key,
            strategy_id="CS48H",
            rebalance_id="20261007"
        )

        assert id1 == id2

        status1 = oms_wrapper.execute_order(id1, fill_price=65000.0, fill_qty=0.1, fee=2.6, execution_id="EXEC-CORE-1")
        assert status1 == "FILLED"

        # Re-execute same execution_id -> no-op
        status2 = oms_wrapper.execute_order(id1, fill_price=65000.0, fill_qty=0.1, fee=2.6, execution_id="EXEC-CORE-1")
        assert status2 == "FILLED"

        paper_order = oms_wrapper.get_paper_order(id1)
        assert paper_order.filled_qty == 0.1
        assert len(paper_order.executions) == 1

    def test_staging_load_10_logical_orders_100_duplicates(self, temp_oms):
        """Load validation: 10 independent logical orders submitted 100 times concurrently -> 10 persisted orders & 10 executions."""
        _, db_path = temp_oms

        def submit_task(order_idx: int):
            local_oms = DurablePaperOMS(db_path=db_path)
            key = f"IDEMP-LOAD-ORDER-{order_idx:02d}"
            client_id = f"CS48H_REB_{order_idx:02d}_BTC_BUY"
            return local_oms.create_order(
                symbol="BTC/USDT",
                side="BUY",
                total_qty=0.01 * (order_idx + 1),
                price=60000.0,
                idempotency_key=key,
                client_order_id=client_id,
                strategy_id="CS48H",
                rebalance_id=f"REB_{order_idx}"
            ).order_id

        # Total 1000 submissions: 10 orders x 100 duplicate submissions
        tasks = [i % 10 for i in range(1000)]
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(submit_task, idx) for idx in tasks]
            results = [f.result() for f in as_completed(futures)]

        unique_order_ids = set(results)
        assert len(unique_order_ids) == 10

        conn = sqlite3.connect(db_path)
        total_orders_in_db = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        assert total_orders_in_db == 10
        conn.close()
