"""
Paper-Trading Order & Position State Machine
=============================================
P2-1, P2-2, P2-3 & P2-4: Formally defined, deterministic, testable state machine for paper-trading order
lifecycles, position management, portfolio state invariants, idempotency, partial-fill execution,
and durable crash recovery with deterministic state replay.

Features:
- Explicit OrderState, OrderEventType, OrderRejectionReason, and CrashPoint enums.
- Deterministic transition matrix with strict validation and terminal state protection.
- Strong quantity and price invariants: strict non-negativity, remaining quantity calculation, overfill rejection.
- Multi-price execution handling with exact Volume-Weighted Average Price (VWAP) calculation.
- Partial fill lifecycles: partial -> partial -> filled, partial -> cancelled, partial -> expired.
- Rejection lifecycle with normalized auditable rejection reasons.
- Strong idempotency model: deterministic logical order keys, stable client_order_id, request fingerprinting.
- Detection and safe rejection of Idempotency Conflicts (same key, different economic parameters).
- Execution event deduplication protecting against double-fills, double cash mutation, and fee inflation.
- Durable crash recovery: crash-safe atomic snapshot persistence (write-to-tmp + atomic replace) and
  authoritative deterministic execution ledger replay with PRAGMA integrity verification.
- Safe failure mode (trading halt) upon unrecoverable corruption.
"""

from enum import Enum
import os
import json
import uuid
import logging
import sqlite3
import threading
import hashlib
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("PaperStateMachine")


# =====================================================================
# Domain Exceptions
# =====================================================================

class PaperTradingError(Exception):
    """Base domain exception for paper-trading errors."""
    pass


class InvalidOrderTransition(PaperTradingError):
    """Raised when an illegal order state transition is attempted."""
    def __init__(self, order_id: Union[int, str], from_state: "OrderState", event_type: "OrderEventType", message: str = ""):
        self.order_id = order_id
        self.from_state = from_state
        self.event_type = event_type
        super().__init__(
            message or f"Illegal transition for Order {order_id}: cannot process '{event_type.value}' from state '{from_state.value}'."
        )


class OrderInvariantViolation(PaperTradingError):
    """Raised when an invariant (e.g. quantity, overfill, position mismatch) is violated."""
    pass


class OverfillRejected(OrderInvariantViolation):
    """Raised when an execution fill exceeds the total order quantity."""
    def __init__(self, order_id: Union[int, str], current_filled: float, attempted_fill: float, total_qty: float):
        self.order_id = order_id
        self.current_filled = current_filled
        self.attempted_fill = attempted_fill
        self.total_qty = total_qty
        super().__init__(
            f"OVERFILL_REJECTED for Order {order_id}: Attempted fill of {attempted_fill:.8f} with current filled {current_filled:.8f} exceeds total quantity {total_qty:.8f}."
        )


class IdempotencyConflict(PaperTradingError):
    """Raised when an order request reuses an existing idempotency key or client_order_id with different economic parameters."""
    pass


class RecoveryFailureError(PaperTradingError):
    """Raised when state recovery encounters severe corruption or unresolvable integrity failures, halting trading."""
    pass


# =====================================================================
# Enums
# =====================================================================

class OrderState(str, Enum):
    """Explicit order lifecycle states."""
    CREATED = "CREATED"                    # Order instantiated locally
    SUBMITTED = "SUBMITTED"                # Order dispatched to paper execution queue
    ACKNOWLEDGED = "ACKNOWLEDGED"          # Order received and acknowledged by paper exchange
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Order partially filled
    FILLED = "FILLED"                      # Order 100% executed (Terminal)
    REJECTED = "REJECTED"                  # Order rejected by validation/risk (Terminal)
    CANCELLED = "CANCELLED"                # Order cancelled before complete fill (Terminal)
    EXPIRED = "EXPIRED"                    # Order timed out / expired (Terminal)
    UNKNOWN = "UNKNOWN"                    # Broker outcome uncertain post-send (Non-terminal)

    @property
    def is_terminal(self) -> bool:
        """Returns True if state is terminal and cannot transition further."""
        return self in (OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED, OrderState.EXPIRED)


class OrderEventType(str, Enum):
    """Events driving order lifecycle transitions."""
    SUBMIT = "SUBMIT"
    ACKNOWLEDGE = "ACKNOWLEDGE"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILL = "FILL"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    EXPIRE = "EXPIRE"
    UNCERTAIN = "UNCERTAIN"


class OrderRejectionReason(str, Enum):
    """Normalized domain rejection codes."""
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    INVALID_PRICE = "INVALID_PRICE"
    RISK_LIMIT = "RISK_LIMIT"
    EXPOSURE_LIMIT = "EXPOSURE_LIMIT"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    MARKET_CLOSED = "MARKET_CLOSED"
    ORDER_EXPIRED = "ORDER_EXPIRED"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    INVALID_STATE = "INVALID_STATE"
    OVERFILL = "OVERFILL"


class CrashPoint(str, Enum):
    """Deterministic simulation crash points for crash-recovery testing."""
    BEFORE_ORDER_PERSIST = "BEFORE_ORDER_PERSIST"
    AFTER_ORDER_PERSIST = "AFTER_ORDER_PERSIST"
    AFTER_STATE_TRANSITION = "AFTER_STATE_TRANSITION"
    BEFORE_EXECUTION_PERSIST = "BEFORE_EXECUTION_PERSIST"
    AFTER_EXECUTION_PERSIST = "AFTER_EXECUTION_PERSIST"
    BEFORE_PORTFOLIO_UPDATE = "BEFORE_PORTFOLIO_UPDATE"
    AFTER_PORTFOLIO_UPDATE = "AFTER_PORTFOLIO_UPDATE"
    BEFORE_SNAPSHOT = "BEFORE_SNAPSHOT"
    AFTER_SNAPSHOT = "AFTER_SNAPSHOT"
    DURING_TRANSACTION = "DURING_TRANSACTION"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionSide(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


# =====================================================================
# Idempotency Helpers & Fingerprinting
# =====================================================================

def compute_request_fingerprint(
    symbol: str,
    side: Union[OrderSide, str],
    order_qty: float,
    price: float = 0.0,
    order_type: str = "MARKET",
    strategy_id: str = "",
    rebalance_id: str = "",
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Computes a deterministic SHA-256 fingerprint of the canonical economic order parameters.
    """
    norm_symbol = symbol.upper().replace(":", "").replace("/", "")
    norm_side = side.value if isinstance(side, OrderSide) else str(side).upper()
    norm_qty = f"{round(float(order_qty), 8):.8f}"
    norm_price = f"{round(float(price), 8):.8f}"
    norm_type = str(order_type).upper()
    norm_strat = str(strategy_id).strip()
    norm_reb = str(rebalance_id).strip()
    
    canonical_payload = f"{norm_symbol}|{norm_side}|{norm_qty}|{norm_price}|{norm_type}|{norm_strat}|{norm_reb}"
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def generate_idempotency_key(
    strategy_id: str,
    symbol: str,
    side: Union[OrderSide, str],
    rebalance_id: str,
    signal_id: Optional[str] = None,
    strategy_version: str = "v1"
) -> str:
    """
    Generates a deterministic logical order key representing a unique trading decision.
    """
    norm_symbol = symbol.upper().replace(":", "").replace("/", "")
    norm_side = side.value if isinstance(side, OrderSide) else str(side).upper()
    raw = f"{strategy_id}|{strategy_version}|{rebalance_id}|{signal_id or ''}|{norm_symbol}|{norm_side}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"IDEMP-{digest}"


def generate_client_order_id(
    strategy_id: str,
    symbol: str,
    side: Union[OrderSide, str],
    rebalance_id: str,
    sequence: int = 1
) -> str:
    """
    Generates a deterministic client order identifier.
    """
    sym_clean = symbol.upper().replace("/", "").replace(":", "")
    reb_clean = rebalance_id.replace("-", "").replace(":", "").replace("T", "_")[:15]
    strat_prefix = strategy_id.replace("_", "")[:6].upper() or "STRAT"
    norm_side = side.value if isinstance(side, OrderSide) else str(side).upper()
    return f"{strat_prefix}_{reb_clean}_{sym_clean}_{norm_side}_{sequence:03d}"


# =====================================================================
# State Transition Matrix
# =====================================================================

LEGAL_TRANSITIONS: Dict[OrderState, Dict[OrderEventType, OrderState]] = {
    OrderState.CREATED: {
        OrderEventType.SUBMIT: OrderState.SUBMITTED,
        OrderEventType.CANCEL: OrderState.CANCELLED,
        OrderEventType.REJECT: OrderState.REJECTED,
        OrderEventType.EXPIRE: OrderState.EXPIRED,
    },
    OrderState.SUBMITTED: {
        OrderEventType.ACKNOWLEDGE: OrderState.ACKNOWLEDGED,
        OrderEventType.FILL: OrderState.FILLED,                  # Fast-path atomic fill in immediate paper mode
        OrderEventType.PARTIAL_FILL: OrderState.PARTIALLY_FILLED,
        OrderEventType.REJECT: OrderState.REJECTED,
        OrderEventType.CANCEL: OrderState.CANCELLED,
        OrderEventType.EXPIRE: OrderState.EXPIRED,
        OrderEventType.UNCERTAIN: OrderState.UNKNOWN,
    },
    OrderState.ACKNOWLEDGED: {
        OrderEventType.PARTIAL_FILL: OrderState.PARTIALLY_FILLED,
        OrderEventType.FILL: OrderState.FILLED,
        OrderEventType.REJECT: OrderState.REJECTED,
        OrderEventType.CANCEL: OrderState.CANCELLED,
        OrderEventType.EXPIRE: OrderState.EXPIRED,
        OrderEventType.UNCERTAIN: OrderState.UNKNOWN,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderEventType.PARTIAL_FILL: OrderState.PARTIALLY_FILLED,
        OrderEventType.FILL: OrderState.FILLED,
        OrderEventType.CANCEL: OrderState.CANCELLED,
        OrderEventType.EXPIRE: OrderState.EXPIRED,
        OrderEventType.UNCERTAIN: OrderState.UNKNOWN,
    },
    OrderState.UNKNOWN: {
        OrderEventType.ACKNOWLEDGE: OrderState.ACKNOWLEDGED,
        OrderEventType.PARTIAL_FILL: OrderState.PARTIALLY_FILLED,
        OrderEventType.FILL: OrderState.FILLED,
        OrderEventType.REJECT: OrderState.REJECTED,
        OrderEventType.CANCEL: OrderState.CANCELLED,
        OrderEventType.EXPIRE: OrderState.EXPIRED,
        OrderEventType.UNCERTAIN: OrderState.UNKNOWN,
    },
    # Terminal states have no legal outgoing transitions
    OrderState.FILLED: {},
    OrderState.REJECTED: {},
    OrderState.CANCELLED: {},
    OrderState.EXPIRED: {},
}


# =====================================================================
# Event & Execution Models
# =====================================================================

@dataclass
class OrderEvent:
    """Structured, immutable audit record of a state transition event."""
    event_id: str
    order_id: Union[int, str]
    event_type: OrderEventType
    event_timestamp: str
    processing_timestamp: str
    previous_state: OrderState
    new_state: OrderState
    quantity: float = 0.0
    price: float = 0.0
    fee: float = 0.0
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "order_id": str(self.order_id),
            "event_type": self.event_type.value,
            "event_timestamp": self.event_timestamp,
            "processing_timestamp": self.processing_timestamp,
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
            "quantity": self.quantity,
            "price": self.price,
            "fee": self.fee,
            "reason": self.reason,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OrderEvent":
        return cls(
            event_id=d["event_id"],
            order_id=d["order_id"],
            event_type=OrderEventType(d["event_type"]),
            event_timestamp=d["event_timestamp"],
            processing_timestamp=d["processing_timestamp"],
            previous_state=OrderState(d["previous_state"]),
            new_state=OrderState(d["new_state"]),
            quantity=float(d.get("quantity", 0.0)),
            price=float(d.get("price", 0.0)),
            fee=float(d.get("fee", 0.0)),
            reason=d.get("reason", ""),
            metadata=d.get("metadata", {})
        )


@dataclass
class OrderExecution:
    """Individual fill execution record."""
    execution_id: str
    order_id: Union[int, str]
    fill_price: float
    fill_qty: float
    fee: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =====================================================================
# State Machine Managed Order Model
# =====================================================================

class PaperOrder:
    """
    Durable, invariant-enforcing Paper Order representation.
    """
    def __init__(
        self,
        order_id: Union[int, str],
        symbol: str,
        side: Union[OrderSide, str],
        order_qty: float,
        price: float = 0.0,
        state: Union[OrderState, str] = OrderState.CREATED,
        filled_qty: float = 0.0,
        average_fill_price: float = 0.0,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        client_order_id: Optional[str] = None,
        request_fingerprint: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        if order_qty <= 0:
            raise OrderInvariantViolation(f"order_qty must be strictly positive, got {order_qty}")

        self.order_id = order_id
        self.symbol = symbol.upper().replace(":", "")
        self.side = OrderSide(side.upper()) if isinstance(side, str) else side
        self.order_qty = float(order_qty)
        self.price = float(price)
        self.state = OrderState(state.upper()) if isinstance(state, str) else state
        self.filled_qty = float(filled_qty)
        self.average_fill_price = float(average_fill_price)
        
        now_iso = datetime.now(timezone.utc).isoformat()
        self.created_at = created_at or now_iso
        self.updated_at = updated_at or now_iso
        self.idempotency_key = idempotency_key
        self.client_order_id = client_order_id
        self.request_fingerprint = request_fingerprint
        self.metadata = metadata or {}

        self.executions: List[OrderExecution] = []
        self.event_history: List[OrderEvent] = []
        self._processed_event_ids: set = set()
        self._processed_execution_ids: set = set()

        self._validate_invariants()

    @property
    def remaining_qty(self) -> float:
        """Remaining unfilled quantity."""
        return max(0.0, round(self.order_qty - self.filled_qty, 8))

    @property
    def is_terminal(self) -> bool:
        return self.state.is_terminal

    def _validate_invariants(self):
        """Enforces all core state invariants."""
        if self.order_qty <= 0:
            raise OrderInvariantViolation(f"Order quantity must be positive: {self.order_qty}")
        if self.filled_qty < 0:
            raise OrderInvariantViolation(f"Filled quantity cannot be negative: {self.filled_qty}")
        if round(self.filled_qty, 8) > round(self.order_qty, 8):
            raise OverfillRejected(self.order_id, self.filled_qty, 0.0, self.order_qty)
        if self.state == OrderState.FILLED and round(self.filled_qty, 8) != round(self.order_qty, 8):
            raise OrderInvariantViolation(
                f"Order in FILLED state must have filled_qty == order_qty ({self.filled_qty} != {self.order_qty})"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes order state to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_qty": self.order_qty,
            "price": self.price,
            "state": self.state.value,
            "filled_qty": self.filled_qty,
            "remaining_qty": self.remaining_qty,
            "average_fill_price": self.average_fill_price,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "idempotency_key": self.idempotency_key,
            "client_order_id": self.client_order_id,
            "request_fingerprint": self.request_fingerprint,
            "metadata": self.metadata,
            "executions": [e.to_dict() for e in self.executions],
            "event_history": [ev.to_dict() for ev in self.event_history]
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PaperOrder":
        """Deserializes order state, mapping legacy SQLite statuses seamlessly."""
        raw_state = d.get("state") or d.get("status") or "CREATED"
        state_map = {
            "PENDING": OrderState.SUBMITTED,
            "PARTIAL": OrderState.PARTIALLY_FILLED,
            "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
            "FILLED": OrderState.FILLED,
            "CANCELED": OrderState.CANCELLED,
            "CANCELLED": OrderState.CANCELLED,
            "REJECTED": OrderState.REJECTED,
            "CREATED": OrderState.CREATED,
            "SUBMITTED": OrderState.SUBMITTED,
            "ACKNOWLEDGED": OrderState.ACKNOWLEDGED,
            "EXPIRED": OrderState.EXPIRED
        }
        order_state = state_map.get(raw_state.upper(), OrderState[raw_state.upper()] if raw_state.upper() in OrderState.__members__ else OrderState.CREATED)

        total_qty = float(d.get("order_qty", d.get("total_qty", 1.0)))
        filled_qty = float(d.get("filled_qty", 0.0))

        order = cls(
            order_id=d.get("order_id", d.get("id", 0)),
            symbol=d.get("symbol", "BTC/USDT"),
            side=d.get("side", "BUY"),
            order_qty=total_qty,
            price=float(d.get("price", 0.0)),
            state=order_state,
            filled_qty=filled_qty,
            average_fill_price=float(d.get("average_fill_price", 0.0)),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            idempotency_key=d.get("idempotency_key"),
            client_order_id=d.get("client_order_id"),
            request_fingerprint=d.get("request_fingerprint"),
            metadata=d.get("metadata", {})
        )

        for ex_dict in d.get("executions", []):
            ex_obj = OrderExecution(**ex_dict)
            order.executions.append(ex_obj)
            order._processed_execution_ids.add(ex_obj.execution_id)

        for ev_dict in d.get("event_history", []):
            ev = OrderEvent.from_dict(ev_dict)
            order.event_history.append(ev)
            order._processed_event_ids.add(ev.event_id)

        return order


# =====================================================================
# Canonical State Transition Engine
# =====================================================================

class PaperStateMachine:
    """
    Authoritative state transition engine.
    Ensures safe, deterministic, invariant-validated state transitions with duplicate-event idempotency
    and partial fill / multi-price / cancellation / rejection handling.
    """

    @staticmethod
    def transition_order(
        order: PaperOrder,
        event_type: Union[OrderEventType, str],
        fill_qty: float = 0.0,
        fill_price: float = 0.0,
        fee: float = 0.0,
        reason: str = "",
        rejection_reason: Optional[Union[OrderRejectionReason, str]] = None,
        event_id: Optional[str] = None,
        event_timestamp: Optional[str] = None,
        execution_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[PaperOrder, OrderEvent]:
        """
        Canonical transition function.
        Validates the transition, applies state updates, enforces invariants,
        records audit events, and logs structured output.
        """
        evt_type = OrderEventType(event_type.upper()) if isinstance(event_type, str) else event_type
        now_iso = datetime.now(timezone.utc).isoformat()
        evt_ts = event_timestamp or now_iso
        evt_id = event_id or str(uuid.uuid4())
        exec_id = execution_id or (str(uuid.uuid4()) if evt_type in (OrderEventType.FILL, OrderEventType.PARTIAL_FILL) else None)
        meta = dict(metadata or {})

        if rejection_reason:
            rej_code = rejection_reason.value if isinstance(rejection_reason, OrderRejectionReason) else str(rejection_reason)
            meta["rejection_reason"] = rej_code
            if not reason:
                reason = rej_code

        # 1. Idempotency Check: if event_id already processed, return no-op
        if evt_id in order._processed_event_ids:
            logger.info(f"IDEMPOTENT_NOOP: Event {evt_id} already processed for Order {order.order_id}")
            existing = next((e for e in order.event_history if e.event_id == evt_id), None)
            if existing:
                return order, existing

        # 1b. Execution Idempotency Check: if execution_id already processed for fill events, return no-op
        if exec_id and exec_id in order._processed_execution_ids:
            logger.info(f"EXECUTION_REUSED: Execution {exec_id} already applied to Order {order.order_id}")
            noop_event = OrderEvent(
                event_id=evt_id,
                order_id=order.order_id,
                event_type=evt_type,
                event_timestamp=evt_ts,
                processing_timestamp=now_iso,
                previous_state=order.state,
                new_state=order.state,
                quantity=fill_qty,
                price=fill_price,
                reason=f"Idempotent duplicate execution {exec_id}",
                metadata=meta
            )
            return order, noop_event

        # 2. Check if re-issuing an identical terminal state as a benign duplicate event
        if order.is_terminal and evt_type.value == order.state.value:
            logger.info(f"IDEMPOTENT_TERMINAL_NOOP: Order {order.order_id} is already in terminal state {order.state.value}")
            noop_event = OrderEvent(
                event_id=evt_id,
                order_id=order.order_id,
                event_type=evt_type,
                event_timestamp=evt_ts,
                processing_timestamp=now_iso,
                previous_state=order.state,
                new_state=order.state,
                quantity=fill_qty,
                price=fill_price,
                reason="Idempotent duplicate terminal event",
                metadata=meta
            )
            return order, noop_event

        # 3. Check legal transition
        allowed_events = LEGAL_TRANSITIONS.get(order.state, {})
        if evt_type not in allowed_events:
            msg = f"Invalid transition: cannot process '{evt_type.value}' on order {order.order_id} in state '{order.state.value}'."
            logger.error(f"ORDER_STATE_TRANSITION_REJECTED order_id={order.order_id} from={order.state.value} event={evt_type.value}")
            raise InvalidOrderTransition(order.order_id, order.state, evt_type, msg)

        target_state = allowed_events[evt_type]
        prev_state = order.state

        # 4. Fill-specific validations & Overfill Protection
        if evt_type in (OrderEventType.FILL, OrderEventType.PARTIAL_FILL):
            if fill_qty <= 0:
                raise OrderInvariantViolation(f"Fill quantity must be strictly positive: {fill_qty}")
            if fill_price <= 0:
                raise OrderInvariantViolation(f"Fill price must be strictly positive: {fill_price}")

            new_total_filled = round(order.filled_qty + fill_qty, 8)
            if new_total_filled > round(order.order_qty, 8):
                logger.warning(
                    f"OVERFILL_REJECTED order_id={order.order_id} current_filled={order.filled_qty} "
                    f"attempted_fill={fill_qty} order_qty={order.order_qty}"
                )
                raise OverfillRejected(order.order_id, order.filled_qty, fill_qty, order.order_qty)

            # Auto-promote to FILLED if this partial fill completes the total quantity
            if new_total_filled == round(order.order_qty, 8):
                target_state = OrderState.FILLED

            # Calculate Quantity-Weighted Average Fill Price (VWAP)
            current_cost = sum(ex.fill_qty * ex.fill_price for ex in order.executions)
            added_cost = fill_qty * fill_price
            order.average_fill_price = round((current_cost + added_cost) / new_total_filled, 8)
            order.filled_qty = new_total_filled

            # Record execution
            exec_record = OrderExecution(
                execution_id=exec_id,
                order_id=order.order_id,
                fill_price=fill_price,
                fill_qty=fill_qty,
                fee=fee,
                timestamp=evt_ts
            )
            order.executions.append(exec_record)
            order._processed_execution_ids.add(exec_id)

        # 5. Apply state transition
        order.state = target_state
        order.updated_at = now_iso

        # 6. Validate invariants post-transition
        order._validate_invariants()

        # 7. Record event
        event = OrderEvent(
            event_id=evt_id,
            order_id=order.order_id,
            event_type=evt_type,
            event_timestamp=evt_ts,
            processing_timestamp=now_iso,
            previous_state=prev_state,
            new_state=target_state,
            quantity=fill_qty,
            price=fill_price,
            fee=fee,
            reason=reason,
            metadata=meta
        )
        order.event_history.append(event)
        order._processed_event_ids.add(evt_id)

        # 8. Structured Observability Logging
        logger.info(
            f"ORDER_STATE_TRANSITION order_id={order.order_id} symbol={order.symbol} side={order.side.value} "
            f"previous_state={prev_state.value} event={evt_type.value} new_state={target_state.value} "
            f"filled_qty={order.filled_qty}/{order.order_qty} avg_price=${order.average_fill_price:.4f} ts={now_iso}"
        )

        if target_state == OrderState.PARTIALLY_FILLED:
            logger.info(
                f"PARTIAL_FILL order_id={order.order_id} execution_id={exec_id} "
                f"fill_quantity={fill_qty:.4f} filled_quantity={order.filled_qty:.4f} "
                f"remaining_quantity={order.remaining_qty:.4f} fill_price={fill_price:.4f} vwap={order.average_fill_price:.4f}"
            )
        elif target_state == OrderState.FILLED:
            logger.info(
                f"ORDER_FILLED order_id={order.order_id} total_filled={order.filled_qty:.4f} vwap={order.average_fill_price:.4f}"
            )
        elif target_state == OrderState.CANCELLED:
            logger.info(
                f"ORDER_CANCELLED order_id={order.order_id} filled_qty={order.filled_qty:.4f} remaining_qty={order.remaining_qty:.4f}"
            )
        elif target_state == OrderState.EXPIRED:
            logger.info(
                f"ORDER_EXPIRED order_id={order.order_id} filled_qty={order.filled_qty:.4f} remaining_qty={order.remaining_qty:.4f}"
            )
        elif target_state == OrderState.REJECTED:
            logger.info(
                f"ORDER_REJECTED order_id={order.order_id} reason={reason}"
            )

        return order, event


# =====================================================================
# Position & Portfolio Interaction Engine
# =====================================================================

@dataclass
class PaperPosition:
    """Explicit position representation."""
    symbol: str
    side: PositionSide = PositionSide.FLAT
    size: float = 0.0
    entry_price: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = 0.0
    realized_pnl: float = 0.0
    entry_ts: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "size": self.size,
            "entry_price": self.entry_price,
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price,
            "realized_pnl": self.realized_pnl,
            "entry_ts": self.entry_ts
        }


class PaperPortfolioManager:
    """
    Manages portfolio cash, open positions, and strict order-to-position invariants.
    Protects against duplicate fills and double-counting of executions.
    Provides crash-safe atomic snapshot persistence and authoritative ledger replay.
    """
    def __init__(self, initial_cash: float = 1000.0, fee_rate: float = 0.0004):
        self._initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.fee_rate = float(fee_rate)
        self.positions: Dict[str, PaperPosition] = {}
        self.orders: Dict[Union[int, str], PaperOrder] = {}
        self.applied_execution_ids: set = set()
        self.is_trading_halted: bool = False

    def get_position(self, symbol: str) -> PaperPosition:
        sym = symbol.upper().replace(":", "").replace("/", "")
        if sym not in self.positions:
            self.positions[sym] = PaperPosition(symbol=sym)
        return self.positions[sym]

    def apply_order_fill(
        self,
        order: PaperOrder,
        fill_qty: float,
        fill_price: float,
        fee: float = 0.0,
        execution_id: Optional[str] = None
    ):
        """
        Applies a validated order fill to the position and cash balances.
        Protects against duplicate execution IDs to guarantee exactly-once economic effect.
        """
        if execution_id and execution_id in self.applied_execution_ids:
            logger.warning(f"DUPLICATE_FILL_IGNORED execution_id={execution_id} order_id={order.order_id}")
            return

        if fill_qty <= 0 or fill_price <= 0:
            raise OrderInvariantViolation("Fill quantity and price must be positive.")

        pos = self.get_position(order.symbol)
        trade_cost = fill_qty * fill_price
        actual_fee = fee if fee > 0 else (trade_cost * self.fee_rate)

        now_iso = datetime.now(timezone.utc).isoformat()

        if order.side == OrderSide.BUY:
            # Buying increases Long or reduces/covers Short
            if pos.side == PositionSide.SHORT:
                # Covering short
                pnl = (pos.entry_price - fill_price) * fill_qty - actual_fee
                pos.realized_pnl += pnl
                self.cash += (fill_qty * pos.entry_price) + pnl
                pos.size -= fill_qty
                if pos.size <= 1e-8:
                    pos.size = 0.0
                    pos.side = PositionSide.FLAT
                    pos.entry_price = 0.0
            else:
                # Opening or adding to long
                total_cost = (pos.size * pos.entry_price) + trade_cost
                new_size = pos.size + fill_qty
                pos.entry_price = total_cost / new_size
                pos.size = new_size
                pos.side = PositionSide.LONG
                pos.highest_price = max(pos.highest_price, fill_price) if pos.highest_price > 0 else fill_price
                pos.entry_ts = pos.entry_ts or now_iso
                self.cash -= (trade_cost + actual_fee)

        elif order.side == OrderSide.SELL:
            # Selling reduces Long or opens Short
            if pos.side == PositionSide.LONG:
                # Selling long
                gross_proceeds = fill_qty * fill_price
                pnl = gross_proceeds - (fill_qty * pos.entry_price) - actual_fee
                pos.realized_pnl += pnl
                self.cash += (gross_proceeds - actual_fee)
                pos.size -= fill_qty
                if pos.size <= 1e-8:
                    pos.size = 0.0
                    pos.side = PositionSide.FLAT
                    pos.entry_price = 0.0
            else:
                # Opening or adding to short
                total_short_val = (pos.size * pos.entry_price) + trade_cost
                new_size = pos.size + fill_qty
                pos.entry_price = total_short_val / new_size
                pos.size = new_size
                pos.side = PositionSide.SHORT
                pos.lowest_price = min(pos.lowest_price, fill_price) if pos.lowest_price > 0 else fill_price
                pos.entry_ts = pos.entry_ts or now_iso
                self.cash -= actual_fee

        if execution_id:
            self.applied_execution_ids.add(execution_id)

    def compute_total_equity(self, current_prices: Dict[str, float]) -> float:
        """Computes mark-to-market total portfolio equity."""
        equity = self.cash
        for sym, pos in self.positions.items():
            if pos.side == PositionSide.FLAT or pos.size <= 0:
                continue
            mark_p = current_prices.get(sym, pos.entry_price)
            if pos.side == PositionSide.LONG:
                equity += (pos.size * mark_p)
            elif pos.side == PositionSide.SHORT:
                unrealized = (pos.entry_price - mark_p) * pos.size
                equity += (pos.size * pos.entry_price) + unrealized
        return round(equity, 4)

    def compute_state_checksum(self) -> str:
        """
        Computes a deterministic SHA-256 fingerprint of current economic portfolio state.
        """
        active_pos = []
        for sym in sorted(self.positions.keys()):
            p = self.positions[sym]
            if p.side != PositionSide.FLAT and p.size > 0:
                active_pos.append(f"{sym}:{p.side.value}:{p.size:.8f}:{p.entry_price:.8f}:{p.realized_pnl:.8f}")

        pos_str = "|".join(active_pos)
        canonical = f"CASH={self.cash:.8f}|POS=[{pos_str}]|EXEC_COUNT={len(self.applied_execution_ids)}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def save_snapshot_atomic(self, file_path: str):
        """
        Crash-safe atomic snapshot writer.
        Writes complete JSON payload to a temporary file, flushes & fsyncs, and performs an atomic replace.
        """
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        tmp_path = f"{file_path}.tmp.{uuid.uuid4().hex}"

        snapshot_data = {
            "version": 1,
            "cash": self.cash,
            "fee_rate": self.fee_rate,
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "applied_execution_ids": list(self.applied_execution_ids),
            "state_checksum": self.compute_state_checksum(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, file_path)
        logger.info(f"SNAPSHOT_SAVED path={file_path} checksum={snapshot_data['state_checksum']}")

    def load_snapshot(self, file_path: str) -> bool:
        """
        Loads and validates portfolio state from snapshot file.
        Returns True if successful, False if file does not exist or is corrupted.
        """
        if not os.path.exists(file_path):
            return False

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.cash = float(data["cash"])
            self.fee_rate = float(data.get("fee_rate", self.fee_rate))
            self.applied_execution_ids = set(data.get("applied_execution_ids", []))
            self.positions = {}
            for sym, pdict in data.get("positions", {}).items():
                self.positions[sym] = PaperPosition(
                    symbol=pdict["symbol"],
                    side=PositionSide(pdict["side"]),
                    size=float(pdict["size"]),
                    entry_price=float(pdict["entry_price"]),
                    highest_price=float(pdict.get("highest_price", 0.0)),
                    lowest_price=float(pdict.get("lowest_price", 0.0)),
                    realized_pnl=float(pdict.get("realized_pnl", 0.0)),
                    entry_ts=pdict.get("entry_ts", "")
                )
            logger.info(f"SNAPSHOT_LOADED path={file_path} cash=${self.cash:.4f}")
            return True
        except Exception as e:
            logger.error(f"SNAPSHOT_LOAD_FAILED path={file_path} error={e}")
            return False

    def replay_from_oms(self, oms: "DurablePaperOMS") -> Dict[str, Any]:
        """
        Reconstructs the authoritative portfolio state from scratch by replaying the SQLite execution ledger.
        """
        logger.info("RECOVERY_STARTED: Replaying execution ledger from SQLite.")
        conn = oms._get_conn()
        cursor = conn.cursor()

        # Check DB integrity
        cursor.execute("PRAGMA integrity_check")
        row = cursor.fetchone()
        if not row or row[0] != "ok":
            self.is_trading_halted = True
            logger.critical("RECOVERY_FAILED: SQLite integrity check failed. TRADING HALTED.")
            raise RecoveryFailureError("SQLite database failed PRAGMA integrity_check.")

        # Reset in-memory state
        self.cash = float(getattr(self, "_initial_cash", 1000.0))
        self.positions = {}
        self.applied_execution_ids = set()

        # Query all executions joined with orders in exact chronological order
        cursor.execute("""
            SELECT e.id, e.order_id, e.fill_price, e.fill_qty, e.fee, e.timestamp, e.execution_id,
                   o.symbol, o.side
            FROM executions e
            JOIN orders o ON e.order_id = o.id
            ORDER BY e.id ASC
        """)
        rows = cursor.fetchall()

        replayed_count = 0
        duplicates_ignored = 0

        for r in rows:
            exec_id = r["execution_id"] or str(r["id"])
            if exec_id in self.applied_execution_ids:
                duplicates_ignored += 1
                continue

            order = PaperOrder(
                order_id=r["order_id"],
                symbol=r["symbol"],
                side=r["side"],
                order_qty=float(r["fill_qty"]),
                price=float(r["fill_price"]),
                state=OrderState.FILLED,
                filled_qty=float(r["fill_qty"])
            )

            self.apply_order_fill(
                order=order,
                fill_qty=r["fill_qty"],
                fill_price=r["fill_price"],
                fee=r["fee"],
                execution_id=exec_id
            )
            replayed_count += 1

        cursor.execute("SELECT COUNT(*) FROM orders")
        orders_count = cursor.fetchone()[0]

        report = {
            "orders_recovered": orders_count,
            "executions_replayed": replayed_count,
            "duplicate_executions_ignored": duplicates_ignored,
            "portfolio_mutations_applied": replayed_count,
            "state_checksum": self.compute_state_checksum(),
            "recovery_status": "SUCCESS"
        }

        logger.info(
            f"RECOVERY_COMPLETE orders={orders_count} executions={replayed_count} "
            f"duplicates={duplicates_ignored} checksum={report['state_checksum']}"
        )
        return report


# =====================================================================
# Database Persistence Layer (Backward-Compatible with oms.db)
# =====================================================================

class DurablePaperOMS:
    """
    SQLite-backed durable Order Management System supporting explicit state machine transitions,
    idempotent duplicate protection, and partial-fill persistence while maintaining 100% backward compatibility.
    """
    def __init__(self, db_path: str = "oms.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=30.0)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def close(self):
        """Closes the current thread-local SQLite connection if open."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def check_integrity(self) -> bool:
        """Runs SQLite PRAGMA integrity_check."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        row = cursor.fetchone()
        return bool(row and row[0] == "ok")

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        # Legacy tables (unchanged base schema)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
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

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            fill_price REAL NOT NULL,
            fill_qty REAL NOT NULL,
            fee REAL DEFAULT 0.0,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        )
        """)

        # Additive P2-1 Audit Event Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_events (
            event_id TEXT PRIMARY KEY,
            order_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            previous_state TEXT NOT NULL,
            new_state TEXT NOT NULL,
            quantity REAL DEFAULT 0.0,
            price REAL DEFAULT 0.0,
            fee REAL DEFAULT 0.0,
            reason TEXT,
            event_timestamp TEXT NOT NULL,
            processing_timestamp TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        )
        """)

        # Safe additive migrations for P2-2 Idempotency
        cursor.execute("PRAGMA table_info(orders)")
        order_cols = {row["name"] for row in cursor.fetchall()}
        if "idempotency_key" not in order_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN idempotency_key TEXT")
        if "client_order_id" not in order_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN client_order_id TEXT")
        if "request_fingerprint" not in order_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN request_fingerprint TEXT")

        cursor.execute("PRAGMA table_info(executions)")
        exec_cols = {row["name"] for row in cursor.fetchall()}
        if "execution_id" not in exec_cols:
            cursor.execute("ALTER TABLE executions ADD COLUMN execution_id TEXT")

        # Create Unique Indexes for Idempotency
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idempotency_key ON orders(idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_client_order_id ON orders(client_order_id) WHERE client_order_id IS NOT NULL"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_executions_execution_id ON executions(execution_id) WHERE execution_id IS NOT NULL"
        )

        conn.commit()

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
    ) -> PaperOrder:
        """
        Creates and persists an initial order in CREATED state with strict idempotency and conflict protection.
        """
        cid = client_order_id or f"CID_{uuid.uuid4().hex[:12]}"
        fingerprint = request_fingerprint or compute_request_fingerprint(
            symbol=symbol,
            side=side,
            order_qty=total_qty,
            price=price,
            order_type=order_type,
            strategy_id=strategy_id,
            rebalance_id=rebalance_id,
            metadata=metadata
        )
        client_order_id = cid

        conn = self._get_conn()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Pre-check idempotency key if provided
        if idempotency_key:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE idempotency_key = ?", (idempotency_key,))
            row = cursor.fetchone()
            if row:
                existing_fp = row["request_fingerprint"]
                if existing_fp and existing_fp != fingerprint:
                    logger.error(
                        f"IDEMPOTENCY_CONFLICT key={idempotency_key} order_id={row['id']} "
                        f"existing_fp={existing_fp} incoming_fp={fingerprint}"
                    )
                    raise IdempotencyConflict(
                        f"Idempotency key '{idempotency_key}' conflict: existing order {row['id']} "
                        f"has different economic parameters."
                    )
                logger.info(
                    f"IDEMPOTENCY_DUPLICATE idempotency_key={idempotency_key} "
                    f"existing_order_id={row['id']} action=REUSE_EXISTING_ORDER existing_state={row['status']}"
                )
                return self.get_order(row["id"])

        # 2. Pre-check client_order_id if provided
        if client_order_id:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,))
            row = cursor.fetchone()
            if row:
                existing_fp = row["request_fingerprint"]
                if existing_fp and existing_fp != fingerprint:
                    logger.error(
                        f"IDEMPOTENCY_CONFLICT client_order_id={client_order_id} order_id={row['id']} "
                        f"existing_fp={existing_fp} incoming_fp={fingerprint}"
                    )
                    raise IdempotencyConflict(
                        f"Client Order ID '{client_order_id}' conflict: existing order {row['id']} "
                        f"has different economic parameters."
                    )
                logger.info(
                    f"IDEMPOTENCY_DUPLICATE client_order_id={client_order_id} "
                    f"existing_order_id={row['id']} action=REUSE_EXISTING_ORDER existing_state={row['status']}"
                )
                return self.get_order(row["id"])

        # 3. Attempt atomic insert protected by uniqueness constraint
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO orders (
                    symbol, side, total_qty, filled_qty, status, created_at, updated_at,
                    idempotency_key, client_order_id, request_fingerprint
                )
                VALUES (?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?)
            """, (
                symbol.upper().replace(":", ""),
                side.upper(),
                float(total_qty),
                OrderState.CREATED.value,
                now_iso,
                now_iso,
                idempotency_key,
                client_order_id,
                fingerprint
            ))
            conn.commit()
            order_id = cursor.lastrowid
            logger.info(
                f"IDEMPOTENCY_REQUEST created order_id={order_id} key={idempotency_key} client_id={client_order_id}"
            )
        except sqlite3.IntegrityError as e:
            # Concurrent race condition: another thread or process inserted the same key
            conn.rollback()
            cursor = conn.cursor()
            row = None
            if idempotency_key:
                cursor.execute("SELECT * FROM orders WHERE idempotency_key = ?", (idempotency_key,))
                row = cursor.fetchone()
            elif client_order_id:
                cursor.execute("SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,))
                row = cursor.fetchone()

            if row:
                existing_fp = row["request_fingerprint"]
                if existing_fp and existing_fp != fingerprint:
                    logger.error(f"IDEMPOTENCY_CONFLICT race key={idempotency_key} order_id={row['id']}")
                    raise IdempotencyConflict(
                        f"Idempotency key conflict under concurrency for order {row['id']}."
                    )
                logger.info(
                    f"IDEMPOTENCY_DUPLICATE race_resolved key={idempotency_key} "
                    f"existing_order_id={row['id']} action=REUSE_EXISTING_ORDER"
                )
                return self.get_order(row["id"])
            else:
                raise e

        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_qty=total_qty,
            price=price,
            state=OrderState.CREATED,
            created_at=now_iso,
            updated_at=now_iso,
            idempotency_key=idempotency_key,
            client_order_id=client_order_id,
            request_fingerprint=fingerprint,
            metadata=metadata
        )
        return order

    def save_transition(self, order: PaperOrder, event: OrderEvent, execution_id: Optional[str] = None):
        """Persists order updates, execution fills, and transition events to SQLite atomically."""
        conn = self._get_conn()
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Update order table
        cursor.execute("""
            UPDATE orders
            SET filled_qty = ?, status = ?, updated_at = ?
            WHERE id = ?
        """, (order.filled_qty, order.state.value, now_iso, order.order_id))

        # Insert execution if fill event
        if event.event_type in (OrderEventType.FILL, OrderEventType.PARTIAL_FILL) and event.quantity > 0:
            exec_id = execution_id or str(uuid.uuid4())
            cursor.execute("""
                INSERT OR IGNORE INTO executions (order_id, fill_price, fill_qty, fee, timestamp, execution_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (order.order_id, event.price, event.quantity, event.fee, event.event_timestamp, exec_id))

        # Insert audit event
        cursor.execute("""
            INSERT OR IGNORE INTO order_events (
                event_id, order_id, event_type, previous_state, new_state,
                quantity, price, fee, reason, event_timestamp, processing_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.event_id, order.order_id, event.event_type.value,
            event.previous_state.value, event.new_state.value,
            event.quantity, event.price, event.fee, event.reason,
            event.event_timestamp, event.processing_timestamp
        ))

        conn.commit()

    def get_order(self, order_id: Union[int, str]) -> Optional[PaperOrder]:
        """Retrieves and deserializes an order with its complete execution history."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            return None

        order_dict = dict(row)
        order = PaperOrder.from_dict(order_dict)

        # Load executions
        cursor.execute("SELECT * FROM executions WHERE order_id = ? ORDER BY id ASC", (order_id,))
        for ex_row in cursor.fetchall():
            ex_dict = dict(ex_row)
            exec_id = ex_dict.get("execution_id") or str(ex_dict["id"])
            order.executions.append(OrderExecution(
                execution_id=exec_id,
                order_id=order_id,
                fill_price=ex_dict["fill_price"],
                fill_qty=ex_dict["fill_qty"],
                fee=ex_dict["fee"],
                timestamp=ex_dict["timestamp"]
            ))
            order._processed_execution_ids.add(exec_id)

        if order.executions:
            total_cost = sum(ex.fill_qty * ex.fill_price for ex in order.executions)
            tot_filled = sum(ex.fill_qty for ex in order.executions)
            if tot_filled > 0:
                order.average_fill_price = round(total_cost / tot_filled, 8)
                order.filled_qty = round(tot_filled, 8)

        # Load events
        cursor.execute("SELECT * FROM order_events WHERE order_id = ? ORDER BY processing_timestamp ASC", (order_id,))
        for ev_row in cursor.fetchall():
            ev_reason = ev_row["reason"] or ""
            ev_meta = {"rejection_reason": ev_reason} if (ev_reason in [r.value for r in OrderRejectionReason]) else {}
            order.event_history.append(OrderEvent(
                event_id=ev_row["event_id"],
                order_id=order_id,
                event_type=OrderEventType(ev_row["event_type"]),
                previous_state=OrderState(ev_row["previous_state"]),
                new_state=OrderState(ev_row["new_state"]),
                quantity=ev_row["quantity"],
                price=ev_row["price"],
                fee=ev_row["fee"],
                reason=ev_reason,
                event_timestamp=ev_row["event_timestamp"],
                processing_timestamp=ev_row["processing_timestamp"],
                metadata=ev_meta
            ))
            order._processed_event_ids.add(ev_row["event_id"])

        return order

    def cancel_order(self, order_id: Union[int, str], reason: str = "") -> PaperOrder:
        """Transitions order to CANCELLED and persists."""
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        PaperStateMachine.transition_order(order, OrderEventType.CANCEL, reason=reason)
        self.save_transition(order, order.event_history[-1])
        return order

    def expire_order(self, order_id: Union[int, str], reason: str = "") -> PaperOrder:
        """Transitions order to EXPIRED and persists."""
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        PaperStateMachine.transition_order(order, OrderEventType.EXPIRE, reason=reason)
        self.save_transition(order, order.event_history[-1])
        return order

    def reject_order(
        self,
        order_id: Union[int, str],
        reason: Union[OrderRejectionReason, str] = OrderRejectionReason.RISK_LIMIT
    ) -> PaperOrder:
        """Transitions order to REJECTED with normalized rejection code."""
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        PaperStateMachine.transition_order(order, OrderEventType.REJECT, rejection_reason=reason)
        self.save_transition(order, order.event_history[-1])
        return order

    def execute_order(
        self,
        order_id: Union[int, str],
        fill_price: float,
        fill_qty: float,
        fee: float = 0.0,
        execution_id: Optional[str] = None
    ) -> PaperOrder:
        """Executes a fill or partial fill on an order and persists."""
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Step through legal transitions from CREATED -> SUBMITTED -> ACKNOWLEDGED if needed
        if order.state == OrderState.CREATED:
            PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
            self.save_transition(order, order.event_history[-1])
        if order.state == OrderState.SUBMITTED:
            PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
            self.save_transition(order, order.event_history[-1])

        is_full = (order.filled_qty + fill_qty >= order.order_qty - 1e-8)
        evt_type = OrderEventType.FILL if is_full else OrderEventType.PARTIAL_FILL

        PaperStateMachine.transition_order(
            order,
            evt_type,
            fill_qty=fill_qty,
            fill_price=fill_price,
            fee=fee,
            execution_id=execution_id
        )
        self.save_transition(order, order.event_history[-1], execution_id=execution_id)
        return order

    def close(self):
        """Closes thread-local database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def get_open_orders(self) -> List[PaperOrder]:
        """Returns all non-terminal open/active orders."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM orders 
            WHERE status NOT IN ('FILLED', 'REJECTED', 'CANCELLED', 'EXPIRED', 'CANCELED')
            ORDER BY id ASC
        """)
        rows = cursor.fetchall()
        orders = []
        for r in rows:
            ord_obj = self.get_order(r["id"])
            if ord_obj:
                orders.append(ord_obj)
        return orders

    def get_all_orders(self) -> List[PaperOrder]:
        """Returns all historical and open orders in OMS."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM orders ORDER BY id ASC")
        rows = cursor.fetchall()
        orders = []
        for r in rows:
            ord_obj = self.get_order(r["id"])
            if ord_obj:
                orders.append(ord_obj)
        return orders

    def get_order_by_idempotency_key(self, idempotency_key: str) -> Optional[PaperOrder]:
        """Retrieves an order by its idempotency key."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM orders WHERE idempotency_key = ?", (idempotency_key,))
        row = cursor.fetchone()
        if row:
            return self.get_order(row["id"])
        return None

    def get_order_by_client_order_id(self, client_order_id: str) -> Optional[PaperOrder]:
        """Retrieves an order by its client order ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM orders WHERE client_order_id = ?", (client_order_id,))
        row = cursor.fetchone()
        if row:
            return self.get_order(row["id"])
        return None
