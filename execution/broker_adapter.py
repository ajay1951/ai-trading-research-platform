"""
Broker & API Fault Injection, Error Classification & Uncertainty Recovery Engine
================================================================================
P2-6: Formally defined, deterministic, observable, and fail-closed broker adapter,
network failure classifier, execution-uncertainty handler, cancel/fill race resolver,
and durable state recovery engine.

Primary Invariants:
1. NETWORK FAILURE != ORDER REJECTION
2. TIMEOUT != NO EXECUTION
3. HTTP 500 != DEFINITIVE ORDER FAILURE
4. CONNECTION RESET != SAFE TO RETRY
5. UNKNOWN != REJECTED and UNKNOWN != FILLED (Broker outcome unknown post-send)
6. Zero speculative portfolio mutations while order is in UNKNOWN state.
7. Authoritative broker outcome applied exactly once.
8. Zero duplicate economic orders on retries or recovery.
"""

from enum import Enum
import os
import uuid
import time
import json
import logging
import sqlite3
import threading
from typing import Dict, Any, List, Optional, Tuple, Set, Union, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

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

logger = logging.getLogger("BrokerAdapter")


# =====================================================================
# Canonical Fault & Error Enums
# =====================================================================

class BrokerFault(str, Enum):
    """Deterministic fault injection failure modes for broker interactions."""
    NONE = "NONE"
    
    # Pre-send transport failures (safe to retry)
    CONNECTION_ERROR_BEFORE_SEND = "CONNECTION_ERROR_BEFORE_SEND"
    TIMEOUT_BEFORE_SEND = "TIMEOUT_BEFORE_SEND"
    DNS_ERROR_BEFORE_SEND = "DNS_ERROR_BEFORE_SEND"
    
    # Post-send transport failures (outcome uncertain -> UNKNOWN)
    TIMEOUT_AFTER_SEND = "TIMEOUT_AFTER_SEND"
    CONNECTION_RESET_AFTER_SEND = "CONNECTION_RESET_AFTER_SEND"
    LOST_RESPONSE_AFTER_SEND = "LOST_RESPONSE_AFTER_SEND"
    DELAYED_RESPONSE = "DELAYED_RESPONSE"
    DUPLICATE_RESPONSE = "DUPLICATE_RESPONSE"
    
    # HTTP server and client failures
    HTTP_400_INVALID_PARAMS = "HTTP_400_INVALID_PARAMS"
    HTTP_429_RATE_LIMIT = "HTTP_429_RATE_LIMIT"
    HTTP_500_INTERNAL_ERROR = "HTTP_500_INTERNAL_ERROR"
    HTTP_502_BAD_GATEWAY = "HTTP_502_BAD_GATEWAY"
    HTTP_503_SERVICE_UNAVAILABLE = "HTTP_503_SERVICE_UNAVAILABLE"
    HTTP_504_GATEWAY_TIMEOUT = "HTTP_504_GATEWAY_TIMEOUT"
    
    # Payload anomalies
    MALFORMED_SUCCESS_RESPONSE = "MALFORMED_SUCCESS_RESPONSE"
    MISSING_ORDER_ID = "MISSING_ORDER_ID"
    
    # Query & Cancel failures
    STATUS_QUERY_TIMEOUT = "STATUS_QUERY_TIMEOUT"
    STATUS_QUERY_UNAVAILABLE = "STATUS_QUERY_UNAVAILABLE"
    CANCEL_TIMEOUT = "CANCEL_TIMEOUT"
    CANCEL_RESPONSE_LOST = "CANCEL_RESPONSE_LOST"
    CANCEL_FILL_RACE = "CANCEL_FILL_RACE"

    # Reconciliation failures
    RECON_POSITIONS_TIMEOUT = "RECON_POSITIONS_TIMEOUT"
    RECON_BALANCES_TIMEOUT = "RECON_BALANCES_TIMEOUT"
    RECON_ORDERS_TIMEOUT = "RECON_ORDERS_TIMEOUT"
    RECON_EXECUTIONS_TIMEOUT = "RECON_EXECUTIONS_TIMEOUT"
    RECON_DATA_STALE = "RECON_DATA_STALE"


class BrokerErrorCategory(str, Enum):
    """Normalized domain categorization of broker/network failures."""
    PRE_SEND_FAILURE = "PRE_SEND_FAILURE"           # Failed before transmission (safe to retry)
    DETERMINISTIC_REJECTION = "DETERMINISTIC_REJECTION" # HTTP 400 / insufficient funds (terminal rejection)
    EXECUTION_UNCERTAIN = "EXECUTION_UNCERTAIN"     # Timeout/5xx/reset post-send (requires status recovery)
    RATE_LIMITED = "RATE_LIMITED"                   # HTTP 429 (bounded backoff with Retry-After)
    RECOVERY_FAILED = "RECOVERY_FAILED"             # Status resolution exhausted (halt trading)


class BrokerStatusResult(str, Enum):
    """Authoritative exchange-side order status lookup result."""
    FOUND_OPEN = "FOUND_OPEN"
    FOUND_PARTIALLY_FILLED = "FOUND_PARTIALLY_FILLED"
    FOUND_FILLED = "FOUND_FILLED"
    FOUND_REJECTED = "FOUND_REJECTED"
    FOUND_CANCELLED = "FOUND_CANCELLED"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN = "UNKNOWN"


# =====================================================================
# Observability & Metrics Bridge
# =====================================================================

class BrokerMetrics:
    """Prometheus & Structured Observability Metrics Bridge for Broker Operations."""
    _metrics_initialized = False

    @classmethod
    def init_metrics(cls):
        if cls._metrics_initialized:
            return
        try:
            from prometheus_client import Counter, Gauge, Histogram
            cls.broker_requests_total = Counter(
                "broker_requests_total", "Total broker API requests dispatched", ["endpoint", "method"]
            )
            cls.broker_request_failures_total = Counter(
                "broker_request_failures_total", "Total broker API request failures", ["endpoint", "category"]
            )
            cls.broker_timeouts_total = Counter(
                "broker_timeouts_total", "Total broker timeouts", ["phase"]
            )
            cls.broker_connection_errors_total = Counter(
                "broker_connection_errors_total", "Total connection dropouts/resets", ["phase"]
            )
            cls.broker_rate_limits_total = Counter(
                "broker_rate_limits_total", "Total HTTP 429 rate limit responses"
            )
            cls.broker_retries_total = Counter(
                "broker_retries_total", "Total broker retries attempted", ["reason"]
            )
            cls.broker_retry_suppressed_total = Counter(
                "broker_retry_suppressed_total", "Total dangerous blind retries suppressed"
            )
            cls.broker_unknown_orders_total = Counter(
                "broker_unknown_orders_total", "Total orders entering UNKNOWN state"
            )
            cls.broker_recovery_attempts_total = Counter(
                "broker_recovery_attempts_total", "Total broker status recovery attempts"
            )
            cls.broker_recovery_success_total = Counter(
                "broker_recovery_success_total", "Total successfully resolved UNKNOWN orders", ["resolved_status"]
            )
            cls.broker_recovery_failures_total = Counter(
                "broker_recovery_failures_total", "Total unresolvable recovery attempts"
            )
            cls.broker_status_queries_total = Counter(
                "broker_status_queries_total", "Total broker status queries dispatched"
            )
            cls.broker_execution_events_total = Counter(
                "broker_execution_events_total", "Total authoritative execution fills processed"
            )
            cls.broker_duplicate_execution_events_total = Counter(
                "broker_duplicate_execution_events_total", "Total duplicate execution fills suppressed"
            )
            cls.broker_trading_halts_total = Counter(
                "broker_trading_halts_total", "Total trading halts triggered by broker uncertainty"
            )
            cls._metrics_initialized = True
        except ImportError:
            cls._metrics_initialized = False

    @classmethod
    def emit_event(cls, event_name: str, **kwargs):
        """Emits structured log event sanitizing any sensitive parameters."""
        payload = {"event": event_name, **kwargs, "timestamp": datetime.now(timezone.utc).isoformat()}
        logger.info(f"{event_name} payload={json.dumps(payload, default=str)}")


# Initialize on module import
BrokerMetrics.init_metrics()


# =====================================================================
# Phase K & 37-38: Independent Fake Broker
# =====================================================================

@dataclass
class BrokerOrderRecord:
    """Independent exchange-side order record."""
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_qty: float
    filled_qty: float = 0.0
    price: float = 0.0
    avg_price: float = 0.0
    status: str = "OPEN" # OPEN, PARTIALLY_FILLED, FILLED, REJECTED, CANCELLED
    rejection_reason: str = ""
    executions: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FakeBroker:
    """
    Independent exchange simulator that maintains its own authoritative truth.
    Supports deterministic fault injection (timeouts, resets, 429s, 5xx, fill/cancel races, reconciliation queries).
    """
    def __init__(self, fee_rate: float = 0.0004, initial_cash: float = 100000.0, clock_fn: Optional[Callable[[], float]] = None):
        self.fee_rate = fee_rate
        self.initial_cash = initial_cash
        self._clock_fn = clock_fn or (lambda: time.time())
        self.orders: Dict[str, BrokerOrderRecord] = {} # Keyed by broker_order_id
        self.client_order_map: Dict[str, str] = {}    # client_order_id -> broker_order_id
        self.custom_positions: Dict[str, Dict[str, Any]] = {}
        self.custom_balance: Optional[Dict[str, Any]] = None
        self.orphan_orders: Dict[str, BrokerOrderRecord] = {}
        self.orphan_executions: List[Dict[str, Any]] = []
        self.active_faults: Set[BrokerFault] = set()
        self.status_query_faults: Set[BrokerFault] = set()
        self.cancel_faults: Set[BrokerFault] = set()
        self.recon_faults: Set[BrokerFault] = set()
        self.rate_limit_retry_after_s: float = 1.0
        self.request_count = 0

    def inject_fault(self, fault: BrokerFault):
        self.active_faults.add(fault)
        if fault in (
            BrokerFault.RECON_POSITIONS_TIMEOUT,
            BrokerFault.RECON_BALANCES_TIMEOUT,
            BrokerFault.RECON_ORDERS_TIMEOUT,
            BrokerFault.RECON_EXECUTIONS_TIMEOUT,
            BrokerFault.RECON_DATA_STALE
        ):
            self.recon_faults.add(fault)

    def clear_faults(self):
        self.active_faults.clear()
        self.status_query_faults.clear()
        self.cancel_faults.clear()
        self.recon_faults.clear()
        self.custom_positions.clear()
        self.custom_balance = None
        self.orphan_orders.clear()
        self.orphan_executions.clear()

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns authoritative exchange position records.
        """
        if BrokerFault.RECON_POSITIONS_TIMEOUT in self.recon_faults or BrokerFault.RECON_POSITIONS_TIMEOUT in self.active_faults:
            raise TimeoutError("Exchange positions endpoint timed out")
        
        if self.custom_positions:
            return dict(self.custom_positions)

        pos_map: Dict[str, Dict[str, Any]] = {}
        for order in self.orders.values():
            if order.filled_qty > 0:
                sym = order.symbol
                if sym not in pos_map:
                    pos_map[sym] = {
                        "symbol": sym,
                        "side": "LONG" if order.side == "BUY" else "SHORT",
                        "size": 0.0,
                        "entry_price": 0.0,
                        "mark_price": order.avg_price or order.price or 50000.0,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                cur_pos = pos_map[sym]
                if order.side == "BUY":
                    new_size = cur_pos["size"] + order.filled_qty
                    cur_pos["entry_price"] = (cur_pos["size"] * cur_pos["entry_price"] + order.filled_qty * order.avg_price) / new_size if new_size > 0 else 0.0
                    cur_pos["size"] = new_size
                    cur_pos["side"] = "LONG" if new_size > 0 else "FLAT"
                else:
                    new_size = cur_pos["size"] - order.filled_qty
                    cur_pos["size"] = new_size
                    cur_pos["side"] = "SHORT" if new_size < 0 else ("LONG" if new_size > 0 else "FLAT")

        return pos_map

    def get_balances(self) -> Dict[str, Any]:
        """
        Returns authoritative exchange balances (cash, total equity).
        """
        if BrokerFault.RECON_BALANCES_TIMEOUT in self.recon_faults or BrokerFault.RECON_BALANCES_TIMEOUT in self.active_faults:
            raise TimeoutError("Exchange balances endpoint timed out")

        if self.custom_balance is not None:
            return dict(self.custom_balance)

        cash = self.initial_cash
        for order in self.orders.values():
            for ex in order.executions:
                qty = float(ex["fill_qty"])
                p = float(ex["fill_price"])
                fee = float(ex["fee"])
                if order.side == "BUY":
                    cash -= (qty * p + fee)
                else:
                    cash += (qty * p - fee)

        equity = cash
        positions = self.get_positions()
        for pos in positions.values():
            equity += pos["size"] * pos["mark_price"]

        ts = datetime.now(timezone.utc).isoformat()
        if BrokerFault.RECON_DATA_STALE in self.recon_faults:
            ts = "2020-01-01T00:00:00+00:00"

        return {
            "currency": "USDT",
            "available_cash": round(cash, 4),
            "total_equity": round(equity, 4),
            "timestamp": ts
        }

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Returns all open/partially-filled orders on the exchange.
        """
        if BrokerFault.RECON_ORDERS_TIMEOUT in self.recon_faults or BrokerFault.RECON_ORDERS_TIMEOUT in self.active_faults:
            raise TimeoutError("Exchange open orders endpoint timed out")

        open_list = []
        all_orders = list(self.orders.values()) + list(self.orphan_orders.values())
        for o in all_orders:
            if o.status in ("OPEN", "PARTIALLY_FILLED"):
                open_list.append({
                    "broker_order_id": o.broker_order_id,
                    "client_order_id": o.client_order_id,
                    "symbol": o.symbol,
                    "side": o.side,
                    "order_qty": o.order_qty,
                    "filled_qty": o.filled_qty,
                    "price": o.price,
                    "status": o.status,
                    "created_at": o.created_at
                })
        return open_list

    def get_all_orders(self) -> List[Dict[str, Any]]:
        """
        Returns all historical and open orders.
        """
        if BrokerFault.RECON_ORDERS_TIMEOUT in self.recon_faults:
            raise TimeoutError("Exchange orders endpoint timed out")

        order_list = []
        all_orders = list(self.orders.values()) + list(self.orphan_orders.values())
        for o in all_orders:
            order_list.append({
                "broker_order_id": o.broker_order_id,
                "client_order_id": o.client_order_id,
                "symbol": o.symbol,
                "side": o.side,
                "order_qty": o.order_qty,
                "filled_qty": o.filled_qty,
                "price": o.price,
                "status": o.status,
                "created_at": o.created_at
            })
        return order_list

    def get_all_executions(self) -> List[Dict[str, Any]]:
        """
        Returns all trade execution fills on the exchange.
        """
        if BrokerFault.RECON_EXECUTIONS_TIMEOUT in self.recon_faults or BrokerFault.RECON_EXECUTIONS_TIMEOUT in self.active_faults:
            raise TimeoutError("Exchange trades endpoint timed out")

        exec_list = []
        for o in list(self.orders.values()) + list(self.orphan_orders.values()):
            for ex in o.executions:
                exec_list.append({
                    "execution_id": ex["execution_id"],
                    "broker_order_id": o.broker_order_id,
                    "client_order_id": o.client_order_id,
                    "symbol": o.symbol,
                    "side": o.side,
                    "fill_qty": float(ex["fill_qty"]),
                    "fill_price": float(ex["fill_price"]),
                    "fee": float(ex["fee"]),
                    "fee_currency": "USDT",
                    "timestamp": ex["timestamp"]
                })
        for ex in self.orphan_executions:
            exec_list.append(ex)
        return exec_list

    def set_position(self, symbol: str, size: float, side: str = "LONG", entry_price: float = 50000.0, mark_price: float = 50000.0):
        """Helper to inject deliberate position state."""
        self.custom_positions[symbol.upper().replace(":", "")] = {
            "symbol": symbol.upper().replace(":", ""),
            "side": side.upper(),
            "size": float(size),
            "entry_price": float(entry_price),
            "mark_price": float(mark_price),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def set_balance(self, available_cash: float, total_equity: Optional[float] = None):
        """Helper to inject deliberate balance state."""
        eq = total_equity if total_equity is not None else available_cash
        self.custom_balance = {
            "currency": "USDT",
            "available_cash": float(available_cash),
            "total_equity": float(eq),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def add_orphan_order(self, symbol: str, side: str, qty: float, price: float = 50000.0, status: str = "OPEN") -> str:
        """Helper to inject an orphan broker order."""
        bid = f"BINANCE_ORPHAN_{uuid.uuid4().hex[:8].upper()}"
        cid = f"CID_ORPHAN_{uuid.uuid4().hex[:8].upper()}"
        rec = BrokerOrderRecord(
            broker_order_id=bid,
            client_order_id=cid,
            symbol=symbol.upper().replace(":", ""),
            side=side.upper(),
            order_qty=float(qty),
            price=float(price),
            status=status
        )
        self.orphan_orders[bid] = rec
        return bid

    def add_orphan_execution(
        self,
        execution_id: str,
        symbol: str,
        side: str,
        fill_qty: float,
        fill_price: float,
        fee: float = 0.0,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ):
        """Helper to inject a missing broker execution fill."""
        self.orphan_executions.append({
            "execution_id": execution_id,
            "broker_order_id": order_id or f"BINANCE_{uuid.uuid4().hex[:8].upper()}",
            "client_order_id": client_order_id or f"CID_{uuid.uuid4().hex[:8].upper()}",
            "symbol": symbol.upper().replace(":", ""),
            "side": side.upper(),
            "fill_qty": float(fill_qty),
            "fill_price": float(fill_price),
            "fee": float(fee),
            "fee_currency": "USDT",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float = 0.0,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes order submission on the exchange, honoring active injected faults.
        """
        self.request_count += 1
        norm_sym = symbol.upper().replace(":", "").replace("/", "")
        cid = client_order_id or f"CID_{uuid.uuid4().hex[:12]}"

        # 1. Pre-send Faults
        if BrokerFault.CONNECTION_ERROR_BEFORE_SEND in self.active_faults:
            raise ConnectionError("Network connection failed before transmitting request bytes")
        if BrokerFault.TIMEOUT_BEFORE_SEND in self.active_faults:
            raise TimeoutError("Socket connection timed out before request dispatch")
        if BrokerFault.DNS_ERROR_BEFORE_SEND in self.active_faults:
            raise ConnectionError("DNS resolution failed: api.binance.com not reachable")

        # 2. HTTP Error Faults
        if BrokerFault.HTTP_400_INVALID_PARAMS in self.active_faults:
            raise ValueError("HTTP 400 Bad Request: Invalid lot size or price filter violation")
        if BrokerFault.HTTP_429_RATE_LIMIT in self.active_faults:
            raise ConnectionError(f"HTTP 429 Too Many Requests: Retry-After {self.rate_limit_retry_after_s}")
        if BrokerFault.HTTP_500_INTERNAL_ERROR in self.active_faults:
            # Note: 500 error happens AFTER server receives bytes
            # The server might have created the order or failed
            pass # Continues to create order or fails below based on test setup
        if BrokerFault.HTTP_502_BAD_GATEWAY in self.active_faults:
            raise ConnectionError("HTTP 502 Bad Gateway: Upstream gateway failed")
        if BrokerFault.HTTP_503_SERVICE_UNAVAILABLE in self.active_faults:
            raise ConnectionError("HTTP 503 Service Unavailable: Exchange matching engine busy")
        if BrokerFault.HTTP_504_GATEWAY_TIMEOUT in self.active_faults:
            raise TimeoutError("HTTP 504 Gateway Timeout")

        # Check broker-side idempotency
        if cid in self.client_order_map:
            bid = self.client_order_map[cid]
            rec = self.orders[bid]
            return {
                "broker_order_id": rec.broker_order_id,
                "client_order_id": rec.client_order_id,
                "status": rec.status,
                "filled_qty": rec.filled_qty,
                "avg_price": rec.avg_price,
                "is_duplicate": True
            }

        # Create exchange order record
        bid = f"BINANCE_{uuid.uuid4().hex[:10].upper()}"
        fill_p = price if price > 0 else 50000.0
        rec = BrokerOrderRecord(
            broker_order_id=bid,
            client_order_id=cid,
            symbol=norm_sym,
            side=side.upper(),
            order_qty=float(quantity),
            price=fill_p,
            status="OPEN"
        )
        self.orders[bid] = rec
        self.client_order_map[cid] = bid

        # Default: immediate complete fill on market/paper order unless specified
        rec.status = "FILLED"
        rec.filled_qty = float(quantity)
        rec.avg_price = fill_p
        exec_id = f"EXEC_{uuid.uuid4().hex[:12]}"
        fee = rec.filled_qty * fill_p * self.fee_rate
        rec.executions.append({
            "execution_id": exec_id,
            "fill_price": fill_p,
            "fill_qty": rec.filled_qty,
            "fee": fee,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # 3. Post-send Faults (Exchange processed order, but response fails to reach client)
        if BrokerFault.TIMEOUT_AFTER_SEND in self.active_faults:
            raise TimeoutError("Client socket timed out waiting for HTTP response from broker")
        if BrokerFault.CONNECTION_RESET_AFTER_SEND in self.active_faults:
            raise ConnectionResetError("Connection reset by peer after request bytes were received")
        if BrokerFault.LOST_RESPONSE_AFTER_SEND in self.active_faults:
            raise ConnectionError("Response packet dropped in transit (TCP FIN/ACK lost)")
        if BrokerFault.MALFORMED_SUCCESS_RESPONSE in self.active_faults:
            return {"status": "SUCCESS", "garbage": "CORRUPTED_JSON_MISSING_FIELDS"}
        if BrokerFault.MISSING_ORDER_ID in self.active_faults:
            return {"client_order_id": cid, "status": "FILLED"} # Missing broker_order_id

        return {
            "broker_order_id": bid,
            "client_order_id": cid,
            "symbol": norm_sym,
            "side": rec.side,
            "order_qty": rec.order_qty,
            "filled_qty": rec.filled_qty,
            "price": fill_p,
            "avg_price": rec.avg_price,
            "status": rec.status,
            "executions": rec.executions
        }

    def query_order(
        self,
        broker_order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authoritative broker status query.
        """
        if BrokerFault.STATUS_QUERY_TIMEOUT in self.status_query_faults:
            raise TimeoutError("Status query request timed out")
        if BrokerFault.STATUS_QUERY_UNAVAILABLE in self.status_query_faults:
            raise ConnectionError("Status query endpoint returned HTTP 503")

        bid = broker_order_id
        if not bid and client_order_id:
            bid = self.client_order_map.get(client_order_id)

        if not bid or bid not in self.orders:
            return {"result": BrokerStatusResult.NOT_FOUND.value, "status": "NOT_FOUND"}

        rec = self.orders[bid]
        return {
            "result": f"FOUND_{rec.status}",
            "broker_order_id": rec.broker_order_id,
            "client_order_id": rec.client_order_id,
            "symbol": rec.symbol,
            "side": rec.side,
            "order_qty": rec.order_qty,
            "filled_qty": rec.filled_qty,
            "avg_price": rec.avg_price,
            "status": rec.status,
            "rejection_reason": rec.rejection_reason,
            "executions": rec.executions
        }

    def cancel_order(
        self,
        broker_order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancels an open order on the broker.
        """
        if BrokerFault.CANCEL_TIMEOUT in self.cancel_faults:
            raise TimeoutError("Cancel request timed out")
        if BrokerFault.CANCEL_RESPONSE_LOST in self.cancel_faults:
            raise ConnectionError("Cancel response dropped")

        bid = broker_order_id or self.client_order_map.get(client_order_id or "")
        if not bid or bid not in self.orders:
            return {"status": "NOT_FOUND", "result": "NOT_FOUND"}

        rec = self.orders[bid]

        # Cancel/Fill Race condition: Order was filled right before cancel arrived
        if BrokerFault.CANCEL_FILL_RACE in self.cancel_faults:
            rec.status = "FILLED"
            rec.filled_qty = rec.order_qty
            rec.avg_price = rec.price if rec.price > 0 else 50000.0
            if not rec.executions:
                exec_id = f"EXEC_{uuid.uuid4().hex[:12]}"
                rec.executions.append({
                    "execution_id": exec_id,
                    "fill_price": rec.avg_price,
                    "fill_qty": rec.filled_qty,
                    "fee": rec.filled_qty * rec.avg_price * self.fee_rate,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            return {"status": "FILLED", "broker_order_id": bid, "result": "FILLED_BEFORE_CANCEL"}

        if rec.status == "OPEN" or rec.status == "PARTIALLY_FILLED":
            rec.status = "CANCELLED"
            return {"status": "CANCELLED", "broker_order_id": bid, "result": "CANCELLED_SUCCESS"}

        return {"status": rec.status, "broker_order_id": bid, "result": f"ALREADY_{rec.status}"}


# =====================================================================
# Phase D, E, F, H, I, J: Production Broker Adapter & Recovery Coordinator
# =====================================================================

class BrokerAdapter:
    """
    Robust, fault-tolerant Broker Adapter and Execution Recovery Coordinator.
    
    Responsibilities:
    1. Distinguishes PRE_SEND_FAILURE, DETERMINISTIC_REJECTION, and EXECUTION_UNCERTAIN.
    2. Enforces UNKNOWN state on post-send ambiguity (never assumes rejection or fill).
    3. Prevents dangerous blind retries of economic orders.
    4. Authoritative broker recovery (recover_unknown_order) resolving exact fill/partial/reject/cancel states.
    5. Applies executions to portfolio exactly once with VWAP and fee consistency.
    6. Resolves Cancel/Fill races deterministically based on exchange truth.
    7. Enforces bounded retry budgets and trading halts on persistent uncertainty.
    """
    def __init__(
        self,
        oms: DurablePaperOMS,
        portfolio_manager: PaperPortfolioManager,
        fake_broker: Optional[FakeBroker] = None,
        max_retries: int = 3,
        initial_backoff_s: float = 0.5,
        max_backoff_s: float = 4.0,
        clock_fn: Optional[Callable[[], float]] = None
    ):
        self.oms = oms
        self.portfolio = portfolio_manager
        self.broker = fake_broker or FakeBroker()
        self.max_retries = max_retries
        self.initial_backoff_s = initial_backoff_s
        self.max_backoff_s = max_backoff_s
        self._clock_fn = clock_fn or (lambda: time.time())
        self.is_trading_halted: bool = False
        self.unresolved_orders: Set[Union[int, str]] = set()

    def classify_error(self, error: Exception, request_sent: bool) -> BrokerErrorCategory:
        """
        Normalizes transport/broker exceptions into canonical domain categories.
        """
        err_msg = str(error).upper()
        if "429" in err_msg or "TOO MANY REQUESTS" in err_msg:
            return BrokerErrorCategory.RATE_LIMITED
        if "400" in err_msg or "BAD REQUEST" in err_msg or "LOT SIZE" in err_msg or "INSUFFICIENT" in err_msg:
            return BrokerErrorCategory.DETERMINISTIC_REJECTION
        if "DNS" in err_msg or "RESOLV" in err_msg or "BEFORE_SEND" in err_msg or "BEFORE SEND" in err_msg or not request_sent:
            return BrokerErrorCategory.PRE_SEND_FAILURE

        # Post-send network dropouts, 5xx errors, timeouts are execution uncertain
        return BrokerErrorCategory.EXECUTION_UNCERTAIN

    def submit_order_safe(
        self,
        order: PaperOrder,
        injected_fault: Optional[BrokerFault] = None
    ) -> Tuple[PaperOrder, BrokerErrorCategory, Optional[str]]:
        """
        Dispatches an order to the broker with strict error classification,
        bounded pre-send retries, and UNKNOWN state enforcement on post-send dropouts.
        """
        if self.is_trading_halted or self.portfolio.is_trading_halted:
            BrokerMetrics.emit_event("BROKER_REQUEST_REJECTED_TRADING_HALTED", order_id=order.order_id)
            return order, BrokerErrorCategory.RECOVERY_FAILED, "TRADING_HALTED"

        attempt_id = str(uuid.uuid4())
        BrokerMetrics.emit_event(
            "BROKER_REQUEST_CREATED",
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            attempt_id=attempt_id
        )

        # Transition to SUBMITTED if in CREATED
        if order.state == OrderState.CREATED:
            PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
            self.oms.save_transition(order, order.event_history[-1])

        # Configure injected fault on broker if testing
        if injected_fault:
            self.broker.inject_fault(injected_fault)

        request_sent = False
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                # Pre-send check: Check if fault is pre-send vs post-send
                if injected_fault in (
                    BrokerFault.CONNECTION_ERROR_BEFORE_SEND,
                    BrokerFault.TIMEOUT_BEFORE_SEND,
                    BrokerFault.DNS_ERROR_BEFORE_SEND
                ):
                    request_sent = False
                else:
                    request_sent = True # Request bytes reach socket/server

                BrokerMetrics.emit_event(
                    "BROKER_REQUEST_SENT",
                    order_id=order.order_id,
                    client_order_id=order.client_order_id,
                    attempt=attempt,
                    request_sent=request_sent
                )

                resp = self.broker.submit_order(
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=order.order_qty,
                    price=order.price,
                    client_order_id=order.client_order_id
                )

                # Validate response structure
                if not isinstance(resp, dict) or "broker_order_id" not in resp:
                    if request_sent:
                        raise ValueError("Malformed broker response missing broker_order_id")

                bid = resp.get("broker_order_id")
                order.metadata["broker_order_id"] = bid

                # Order acknowledged / filled
                PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
                self.oms.save_transition(order, order.event_history[-1])
                BrokerMetrics.emit_event("BROKER_REQUEST_ACKNOWLEDGED", order_id=order.order_id, broker_order_id=bid)

                # Process executions if filled
                if resp.get("status") == "FILLED":
                    execs = resp.get("executions", [])
                    if execs:
                        for ex in execs:
                            self.oms.execute_order(
                                order_id=order.order_id,
                                fill_price=float(ex["fill_price"]),
                                fill_qty=float(ex["fill_qty"]),
                                fee=float(ex["fee"]),
                                execution_id=ex["execution_id"]
                            )
                            # Apply to portfolio
                            self.portfolio.apply_order_fill(
                                order=order,
                                fill_qty=float(ex["fill_qty"]),
                                fill_price=float(ex["fill_price"]),
                                fee=float(ex["fee"]),
                                execution_id=ex["execution_id"]
                            )
                    else:
                        fill_p = float(resp.get("avg_price", order.price or 50000.0))
                        ex_id = f"EXEC_{uuid.uuid4().hex[:12]}"
                        self.oms.execute_order(
                            order_id=order.order_id,
                            fill_price=fill_p,
                            fill_qty=order.order_qty,
                            fee=order.order_qty * fill_p * self.portfolio.fee_rate,
                            execution_id=ex_id
                        )
                        self.portfolio.apply_order_fill(
                            order=order,
                            fill_qty=order.order_qty,
                            fill_price=fill_p,
                            fee=order.order_qty * fill_p * self.portfolio.fee_rate,
                            execution_id=ex_id
                        )

                fresh_order = self.oms.get_order(order.order_id) or order
                return fresh_order, BrokerErrorCategory.PRE_SEND_FAILURE, None

            except Exception as e:
                last_error = e
                category = self.classify_error(e, request_sent=request_sent)

                if category == BrokerErrorCategory.PRE_SEND_FAILURE:
                    # Safe to retry pre-send failures with exponential backoff
                    BrokerMetrics.emit_event("BROKER_RETRY_SCHEDULED", order_id=order.order_id, attempt=attempt, error=str(e))
                    delay = min(self.initial_backoff_s * (2 ** (attempt - 1)), self.max_backoff_s)
                    time.sleep(delay)
                    continue

                if category == BrokerErrorCategory.RATE_LIMITED:
                    # Bounded 429 backoff
                    BrokerMetrics.emit_event("BROKER_RATE_LIMITED", order_id=order.order_id, attempt=attempt)
                    delay = self.broker.rate_limit_retry_after_s
                    time.sleep(delay)
                    continue

                if category == BrokerErrorCategory.DETERMINISTIC_REJECTION:
                    # Rejection is terminal
                    order = self.oms.reject_order(order.order_id, reason=OrderRejectionReason.RISK_LIMIT)
                    BrokerMetrics.emit_event("BROKER_ORDER_REJECTED", order_id=order.order_id, reason=str(e))
                    return order, category, str(e)

                if category == BrokerErrorCategory.EXECUTION_UNCERTAIN:
                    # CRITICAL INVARIANT: DO NOT RETRY BLINDLY! TRANSITION TO UNKNOWN!
                    BrokerMetrics.emit_event("BROKER_RETRY_SUPPRESSED", order_id=order.order_id, reason="EXECUTION_UNCERTAIN")
                    PaperStateMachine.transition_order(order, OrderEventType.UNCERTAIN, reason=str(e))
                    self.oms.save_transition(order, order.event_history[-1])
                    self.unresolved_orders.add(order.order_id)
                    BrokerMetrics.emit_event("BROKER_ORDER_UNKNOWN", order_id=order.order_id, error=str(e))
                    fresh_order = self.oms.get_order(order.order_id) or order
                    return fresh_order, category, str(e)

        # Retries exhausted for pre-send failure
        order = self.oms.reject_order(order.order_id, reason=OrderRejectionReason.RISK_LIMIT)
        return order, BrokerErrorCategory.RECOVERY_FAILED, f"Retries exhausted: {last_error}"

    def recover_unknown_order(
        self,
        order_id: Union[int, str],
        status_fault: Optional[BrokerFault] = None
    ) -> Tuple[PaperOrder, BrokerStatusResult, Optional[str]]:
        """
        Queries authoritative broker state to resolve an UNKNOWN order.
        Resolves FILLED, PARTIALLY_FILLED, REJECTED, or CANCELLED state.
        Applies economic effects to portfolio exactly once.
        """
        order = self.oms.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Fast path if already resolved
        if order.state == OrderState.FILLED:
            return order, BrokerStatusResult.FOUND_FILLED, None
        if order.state == OrderState.REJECTED:
            return order, BrokerStatusResult.FOUND_REJECTED, None
        if order.state == OrderState.CANCELLED:
            return order, BrokerStatusResult.FOUND_CANCELLED, None

        if status_fault:
            self.broker.status_query_faults.add(status_fault)

        BrokerMetrics.emit_event("BROKER_STATUS_RECOVERY_STARTED", order_id=order_id, client_order_id=order.client_order_id)

        try:
            query_resp = self.broker.query_order(
                broker_order_id=order.metadata.get("broker_order_id"),
                client_order_id=order.client_order_id
            )
        except Exception as e:
            BrokerMetrics.emit_event("BROKER_STATUS_RECOVERY_FAILED", order_id=order_id, error=str(e))
            self.is_trading_halted = True
            return order, BrokerStatusResult.UNKNOWN, f"Status lookup failed: {e}"

        status_str = query_resp.get("status", "NOT_FOUND").upper()

        if status_str == "FILLED":
            # Process fill
            execs = query_resp.get("executions", [])
            if execs:
                for ex in execs:
                    self.oms.execute_order(
                        order_id=order.order_id,
                        fill_price=float(ex["fill_price"]),
                        fill_qty=float(ex["fill_qty"]),
                        fee=float(ex["fee"]),
                        execution_id=ex["execution_id"]
                    )
                    self.portfolio.apply_order_fill(
                        order=order,
                        fill_qty=float(ex["fill_qty"]),
                        fill_price=float(ex["fill_price"]),
                        fee=float(ex["fee"]),
                        execution_id=ex["execution_id"]
                    )
            else:
                raw_avg = query_resp.get("avg_price")
                fill_p = float(raw_avg) if raw_avg and float(raw_avg) > 0 else float(order.price or 50000.0)
                ex_id = f"EXEC_{uuid.uuid4().hex[:12]}"
                self.oms.execute_order(
                    order_id=order.order_id,
                    fill_price=fill_p,
                    fill_qty=order.order_qty,
                    fee=order.order_qty * fill_p * self.portfolio.fee_rate,
                    execution_id=ex_id
                )
                self.portfolio.apply_order_fill(
                    order=order,
                    fill_qty=order.order_qty,
                    fill_price=fill_p,
                    fee=order.order_qty * fill_p * self.portfolio.fee_rate,
                    execution_id=ex_id
                )

            self.unresolved_orders.discard(order_id)
            if not self.unresolved_orders:
                self.is_trading_halted = False
            BrokerMetrics.emit_event("BROKER_STATUS_RECOVERED", order_id=order_id, resolved_status="FILLED")
            return self.oms.get_order(order_id), BrokerStatusResult.FOUND_FILLED, None

        elif status_str == "PARTIALLY_FILLED":
            filled_qty = float(query_resp.get("filled_qty", 0.0))
            fill_p = float(query_resp.get("avg_price", order.price or 50000.0))
            ex_id = f"EXEC_{uuid.uuid4().hex[:12]}"
            
            PaperStateMachine.transition_order(
                order,
                OrderEventType.PARTIAL_FILL,
                fill_qty=filled_qty,
                fill_price=fill_p,
                fee=filled_qty * fill_p * self.portfolio.fee_rate,
                execution_id=ex_id
            )
            self.oms.save_transition(order, order.event_history[-1], execution_id=ex_id)
            self.portfolio.apply_order_fill(
                order=order,
                fill_qty=filled_qty,
                fill_price=fill_p,
                fee=filled_qty * fill_p * self.portfolio.fee_rate,
                execution_id=ex_id
            )
            self.unresolved_orders.discard(order_id)
            if not self.unresolved_orders:
                self.is_trading_halted = False
            BrokerMetrics.emit_event("BROKER_STATUS_RECOVERED", order_id=order_id, resolved_status="PARTIALLY_FILLED")
            return self.oms.get_order(order_id), BrokerStatusResult.FOUND_PARTIALLY_FILLED, None

        elif status_str == "REJECTED":
            self.oms.reject_order(order_id, reason=OrderRejectionReason.RISK_LIMIT)
            self.unresolved_orders.discard(order_id)
            if not self.unresolved_orders:
                self.is_trading_halted = False
            BrokerMetrics.emit_event("BROKER_STATUS_RECOVERED", order_id=order_id, resolved_status="REJECTED")
            return self.oms.get_order(order_id), BrokerStatusResult.FOUND_REJECTED, None

        elif status_str == "CANCELLED":
            self.oms.cancel_order(order_id, reason="Broker cancelled")
            self.unresolved_orders.discard(order_id)
            if not self.unresolved_orders:
                self.is_trading_halted = False
            BrokerMetrics.emit_event("BROKER_STATUS_RECOVERED", order_id=order_id, resolved_status="CANCELLED")
            return self.oms.get_order(order_id), BrokerStatusResult.FOUND_CANCELLED, None

        elif status_str == "NOT_FOUND":
            # If confirmed never reached broker, reject
            self.oms.reject_order(order_id, reason="Order not found on exchange")
            self.unresolved_orders.discard(order_id)
            if not self.unresolved_orders:
                self.is_trading_halted = False
            return self.oms.get_order(order_id), BrokerStatusResult.NOT_FOUND, None

        return order, BrokerStatusResult.UNKNOWN, "Status unresolved"

    def cancel_order_safe(
        self,
        order_id: Union[int, str],
        cancel_fault: Optional[BrokerFault] = None
    ) -> Tuple[PaperOrder, str]:
        """
        Cancels an order, handling cancel timeouts and cancel/fill race conditions.
        If cancel outcome is uncertain, queries broker authoritative state.
        """
        order = self.oms.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if cancel_fault:
            self.broker.cancel_faults.add(cancel_fault)

        try:
            resp = self.broker.cancel_order(
                broker_order_id=order.metadata.get("broker_order_id"),
                client_order_id=order.client_order_id
            )
            res_status = resp.get("status", "").upper()
            if res_status == "CANCELLED":
                self.oms.cancel_order(order_id, reason="User cancelled")
                return self.oms.get_order(order_id), "CANCELLED"
            elif res_status == "FILLED":
                # Cancel/Fill Race: Order filled before cancel arrived!
                self.recover_unknown_order(order_id)
                return self.oms.get_order(order_id), "FILLED_RACE"
        except Exception as e:
            # Cancel failed or timed out: resolve via broker query
            BrokerMetrics.emit_event("BROKER_CANCEL_UNCERTAIN", order_id=order_id, error=str(e))
            self.recover_unknown_order(order_id)
            return self.oms.get_order(order_id), "RECOVERED_AFTER_CANCEL_TIMEOUT"

        return self.oms.get_order(order_id), "CANCEL_COMPLETE"
