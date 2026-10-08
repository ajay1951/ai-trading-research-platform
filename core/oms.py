import sqlite3
import os
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass

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
    compute_request_fingerprint,
    generate_idempotency_key,
    generate_client_order_id
)


@dataclass
class Order:
    """Legacy Order dataclass for backward-compatibility."""
    id: int
    symbol: str
    side: str
    total_qty: float
    filled_qty: float
    status: str
    created_at: str


class OrderManagementSystem:
    """
    Durable Order Management System backed by SQLite and powered by the formal PaperStateMachine.
    Provides strict lifecycle enforcement, terminal state protection, idempotency, partial fill support,
    and backward compatibility.
    """
    def __init__(self, db_path: str = "oms.db"):
        self.db_path = db_path
        self._durable_oms = DurablePaperOMS(db_path=db_path)
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        return self._durable_oms._get_conn()

    def create_order(
        self,
        symbol: str,
        side: str,
        total_qty: float,
        price: float = 0.0,
        idempotency_key: Optional[str] = None,
        client_order_id: Optional[str] = None,
        request_fingerprint: Optional[str] = None,
        strategy_id: str = "",
        rebalance_id: str = "",
        order_type: str = "MARKET",
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Creates order in CREATED state and persists to database with idempotency protection."""
        order = self._durable_oms.create_order(
            symbol=symbol,
            side=side,
            total_qty=total_qty,
            price=price,
            idempotency_key=idempotency_key,
            client_order_id=client_order_id,
            request_fingerprint=request_fingerprint,
            strategy_id=strategy_id,
            rebalance_id=rebalance_id,
            order_type=order_type,
            metadata=metadata
        )
        return int(order.order_id)

    def execute_order(
        self,
        order_id: int,
        fill_price: float,
        fill_qty: float,
        fee: float = 0.0,
        execution_id: Optional[str] = None
    ) -> str:
        """Executes fill transition through canonical state machine with deduplication."""
        order = self._durable_oms.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # First transition to SUBMITTED / ACKNOWLEDGED if in CREATED
        if order.state == OrderState.CREATED:
            PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
            self._durable_oms.save_transition(order, order.event_history[-1])
            PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
            self._durable_oms.save_transition(order, order.event_history[-1])
        elif order.state == OrderState.SUBMITTED:
            PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
            self._durable_oms.save_transition(order, order.event_history[-1])

        # Apply Fill or Partial Fill
        evt = OrderEventType.FILL if (order.filled_qty + fill_qty >= order.order_qty) else OrderEventType.PARTIAL_FILL
        PaperStateMachine.transition_order(
            order,
            evt,
            fill_qty=fill_qty,
            fill_price=fill_price,
            fee=fee,
            execution_id=execution_id
        )
        self._durable_oms.save_transition(order, order.event_history[-1], execution_id=execution_id)

        return order.state.value

    def cancel_order(self, order_id: int, reason: str = "") -> str:
        """Cancels order and persists."""
        order = self._durable_oms.cancel_order(order_id, reason=reason)
        return order.state.value

    def expire_order(self, order_id: int, reason: str = "") -> str:
        """Expires order and persists."""
        order = self._durable_oms.expire_order(order_id, reason=reason)
        return order.state.value

    def reject_order(
        self,
        order_id: int,
        reason: Union[OrderRejectionReason, str] = OrderRejectionReason.RISK_LIMIT
    ) -> str:
        """Rejects order with normalized rejection reason and persists."""
        order = self._durable_oms.reject_order(order_id, reason=reason)
        return order.state.value

    def get_order(self, order_id: int) -> Optional[Order]:
        """Returns legacy Order dataclass for backward-compatibility."""
        order = self._durable_oms.get_order(order_id)
        if order:
            return Order(
                id=int(order.order_id),
                symbol=order.symbol,
                side=order.side.value,
                total_qty=order.order_qty,
                filled_qty=order.filled_qty,
                status=order.state.value,
                created_at=order.created_at
            )
        return None

    def get_paper_order(self, order_id: int) -> Optional[PaperOrder]:
        """Returns full PaperOrder object with event history."""
        return self._durable_oms.get_order(order_id)

    def get_order_by_idempotency_key(self, idempotency_key: str) -> Optional[PaperOrder]:
        """Retrieves order by idempotency key."""
        return self._durable_oms.get_order_by_idempotency_key(idempotency_key)

    def get_order_by_client_order_id(self, client_order_id: str) -> Optional[PaperOrder]:
        """Retrieves order by client order ID."""
        return self._durable_oms.get_order_by_client_order_id(client_order_id)


# Global OMS Instance
oms = OrderManagementSystem()
