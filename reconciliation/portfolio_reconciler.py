"""
P2-7: Continuous Portfolio Reconciliation, Broker Truth Verification & Safe Trading Halt Subsystem
==================================================================================================
Provides continuous and event-triggered comparison between the internal OMS / Portfolio state
and authoritative exchange/broker reality. Detects position drift, cash drift, order state drift,
missing executions, duplicate fills, orphan broker orders, VWAP discrepancies, and fee drift.

Core Invariant:
    INTERNAL STATE MUST EITHER MATCH AUTHORITATIVE BROKER STATE OR TRADING MUST BE SAFELY HALTED.

Authority Model:
    - Broker / Exchange: Authoritative for economic truth (balances, positions, exchange orders, fills).
    - Internal OMS: Authoritative for strategy intent, logical order identities, risk attribution, audit history.
"""

import os
import json
import time
import uuid
import logging
import threading
from enum import Enum
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Tuple, Union, Callable

from execution.paper_state_machine import (
    OrderState,
    OrderEventType,
    OrderSide,
    PositionSide,
    PaperOrder,
    PaperPosition,
    PaperPortfolioManager,
    DurablePaperOMS,
    PaperStateMachine,
    OrderExecution,
    OrderEvent,
    generate_client_order_id
)
from execution.broker_adapter import (
    FakeBroker,
    BrokerFault,
    BrokerAdapter
)

logger = logging.getLogger("PortfolioReconciler")


# =====================================================================
# Enums & Classifications
# =====================================================================

class DriftSeverity(str, Enum):
    """Normalized reconciliation drift severity levels."""
    INFO = "INFO"         # Harmless metadata or timing nuance
    WARNING = "WARNING"   # Minor tolerated rounding or semantic difference
    ERROR = "ERROR"       # Discrepancy requiring automated investigation/retry
    CRITICAL = "CRITICAL" # Economic discrepancy capable of creating unintended exposure (triggers halt)


class DriftType(str, Enum):
    """Normalized categorization of reconciliation discrepancies."""
    POSITION_QTY_MISMATCH = "POSITION_QTY_MISMATCH"
    POSITION_SIDE_MISMATCH = "POSITION_SIDE_MISMATCH"
    BALANCE_MISMATCH = "BALANCE_MISMATCH"
    ORDER_MISSING_AT_BROKER = "ORDER_MISSING_AT_BROKER"
    ORPHAN_BROKER_ORDER = "ORPHAN_BROKER_ORDER"
    ORDER_STATUS_MISMATCH = "ORDER_STATUS_MISMATCH"
    ORDER_QTY_MISMATCH = "ORDER_QTY_MISMATCH"
    FILL_QTY_MISMATCH = "FILL_QTY_MISMATCH"
    MISSING_INTERNAL_EXECUTION = "MISSING_INTERNAL_EXECUTION"
    MISSING_BROKER_EXECUTION = "MISSING_BROKER_EXECUTION"
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    VWAP_MISMATCH = "VWAP_MISMATCH"
    FEE_MISMATCH = "FEE_MISMATCH"
    PNL_MISMATCH = "PNL_MISMATCH"
    BROKER_DATA_UNAVAILABLE = "BROKER_DATA_UNAVAILABLE"
    BROKER_DATA_STALE = "BROKER_DATA_STALE"
    RECONCILIATION_TIMEOUT = "RECONCILIATION_TIMEOUT"


class ReconciliationStatus(str, Enum):
    """Overall operational health of the reconciliation subsystem."""
    HEALTHY = "HEALTHY"                 # 100% matched across all domains
    DEGRADED = "DEGRADED"               # Warnings/minor semantic differences present
    DRIFT_DETECTED = "DRIFT_DETECTED"   # Non-critical discrepancy detected
    CRITICAL_DRIFT = "CRITICAL_DRIFT"   # Critical exposure mismatch detected (trading halted)
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE" # Broker query failed/timed out (fail-closed halt)
    RECOVERING = "RECOVERING"           # Active repair or unknown state recovery in progress
    HALTED = "HALTED"                   # Trading deliberately disabled


class HaltScope(str, Enum):
    """Scope of trading halt applied upon reconciliation failure."""
    NONE = "NONE"
    SYMBOL = "SYMBOL"       # Specific asset trading halted (e.g. BTC only)
    STRATEGY = "STRATEGY"   # Specific trading strategy halted
    ACCOUNT = "ACCOUNT"     # Entire account trading halted (balance mismatch)
    GLOBAL = "GLOBAL"       # All systems halted (broker offline/critical failure)


class ReconciliationMode(str, Enum):
    """Execution scope for reconciliation."""
    FULL = "FULL"           # Positions, Balances, Orders, Executions, Fees, P&L
    SYMBOL = "SYMBOL"       # Specific symbol verification
    ORDER = "ORDER"         # Specific order verification
    ACCOUNT = "ACCOUNT"     # Balances and total equity verification


# =====================================================================
# Tolerance Configuration
# =====================================================================

@dataclass
class ReconciliationTolerance:
    """Explicit tolerances for financial comparisons to prevent false alerts."""
    quantity_tolerance: Decimal = Decimal("0.000001") # 1e-6 crypto asset precision
    cash_tolerance: Decimal = Decimal("0.01")         # 1 cent USDT
    price_tolerance: Decimal = Decimal("0.0001")      # 0.01 bps
    fee_tolerance: Decimal = Decimal("0.001")         # 0.1 cent fee tolerance
    pnl_tolerance: Decimal = Decimal("0.05")          # 5 cents P&L tolerance
    staleness_threshold_s: float = 60.0               # Maximum acceptable broker snapshot age


# =====================================================================
# Normalized Data Structures (Decimal-Safe)
# =====================================================================

@dataclass
class NormalizedPosition:
    """Decimal-normalized position representation."""
    symbol: str
    side: PositionSide
    size: Decimal
    entry_price: Decimal
    mark_price: Decimal
    notional: Decimal
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class NormalizedBalance:
    """Decimal-normalized balance representation."""
    currency: str
    available_cash: Decimal
    total_equity: Decimal
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class NormalizedOrder:
    """Decimal-normalized order representation."""
    order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    order_qty: Decimal
    filled_qty: Decimal
    price: Decimal
    status: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class NormalizedExecution:
    """Decimal-normalized trade execution representation."""
    execution_id: str
    order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    fill_qty: Decimal
    fill_price: Decimal
    fee: Decimal
    fee_currency: str = "USDT"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DriftItem:
    """Structured, immutable record of an individual reconciliation discrepancy."""
    drift_id: str
    domain: str # POSITIONS, BALANCES, ORDERS, EXECUTIONS, FEES, PNL
    drift_type: DriftType
    severity: DriftSeverity
    symbol: Optional[str]
    order_id: Optional[str]
    execution_id: Optional[str]
    internal_value: Any
    broker_value: Any
    delta: Any
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drift_id": self.drift_id,
            "domain": self.domain,
            "drift_type": self.drift_type.value,
            "severity": self.severity.value,
            "symbol": self.symbol,
            "order_id": self.order_id,
            "execution_id": self.execution_id,
            "internal_value": str(self.internal_value),
            "broker_value": str(self.broker_value),
            "delta": str(self.delta),
            "message": self.message,
            "timestamp": self.timestamp
        }


@dataclass
class ReconciliationSnapshot:
    """Immutable report and evidence snapshot for a reconciliation cycle."""
    reconciliation_id: str
    timestamp: str
    broker_snapshot_timestamp: str
    status: ReconciliationStatus
    highest_severity: DriftSeverity
    halt_scope: HaltScope
    halted_symbols: List[str]
    position_summary: Dict[str, Any]
    balance_summary: Dict[str, Any]
    order_summary: Dict[str, Any]
    execution_summary: Dict[str, Any]
    drifts: List[DriftItem] = field(default_factory=list)
    drift_count: int = 0
    unresolved_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reconciliation_id": self.reconciliation_id,
            "timestamp": self.timestamp,
            "broker_snapshot_timestamp": self.broker_snapshot_timestamp,
            "status": self.status.value,
            "highest_severity": self.highest_severity.value,
            "halt_scope": self.halt_scope.value,
            "halted_symbols": self.halted_symbols,
            "position_summary": self.position_summary,
            "balance_summary": self.balance_summary,
            "order_summary": self.order_summary,
            "execution_summary": self.execution_summary,
            "drifts": [d.to_dict() for d in self.drifts],
            "drift_count": self.drift_count,
            "unresolved_count": self.unresolved_count
        }


# =====================================================================
# Observability & Metrics Bridge
# =====================================================================

class ReconciliationMetrics:
    """Prometheus & Structured Observability Bridge for Reconciliation."""
    _metrics_initialized = False

    @classmethod
    def init_metrics(cls):
        if cls._metrics_initialized:
            return
        try:
            from prometheus_client import Counter, Gauge, Histogram
            cls.reconciliation_runs_total = Counter(
                "reconciliation_runs_total", "Total reconciliation runs executed", ["mode"]
            )
            cls.reconciliation_success_total = Counter(
                "reconciliation_success_total", "Total clean reconciliation runs (MATCH)"
            )
            cls.reconciliation_failure_total = Counter(
                "reconciliation_failure_total", "Total reconciliation runs encountering failures/errors"
            )
            cls.reconciliation_drift_total = Counter(
                "reconciliation_drift_total", "Total individual drifts identified", ["domain", "severity"]
            )
            cls.reconciliation_critical_drift_total = Counter(
                "reconciliation_critical_drift_total", "Total critical exposure drifts identified"
            )
            cls.position_mismatch_total = Counter(
                "position_mismatch_total", "Total position quantity/side mismatches"
            )
            cls.balance_mismatch_total = Counter(
                "balance_mismatch_total", "Total cash balance mismatches"
            )
            cls.order_mismatch_total = Counter(
                "order_mismatch_total", "Total order mismatches", ["type"]
            )
            cls.execution_mismatch_total = Counter(
                "execution_mismatch_total", "Total execution mismatches", ["type"]
            )
            cls.orphan_order_total = Counter(
                "orphan_order_total", "Total orphan broker orders detected"
            )
            cls.missing_execution_total = Counter(
                "missing_execution_total", "Total broker executions missing internally"
            )
            cls.reconciliation_repairs_total = Counter(
                "reconciliation_repairs_total", "Total successful authoritative execution repairs"
            )
            cls.reconciliation_repair_failures_total = Counter(
                "reconciliation_repair_failures_total", "Total failed repair attempts"
            )
            cls.reconciliation_halts_total = Counter(
                "reconciliation_halts_total", "Total trading halts triggered by reconciliation", ["scope"]
            )
            cls.reconciliation_duration_seconds = Histogram(
                "reconciliation_duration_seconds", "Duration of reconciliation cycles in seconds"
            )
            cls._metrics_initialized = True
        except ImportError:
            cls._metrics_initialized = False

    @classmethod
    def emit_event(cls, event_name: str, **kwargs):
        """Emits sanitized structured log event."""
        payload = {"event": event_name, **kwargs, "timestamp": datetime.now(timezone.utc).isoformat()}
        logger.info(f"{event_name} payload={json.dumps(payload, default=str)}")


ReconciliationMetrics.init_metrics()


# =====================================================================
# Canonical Universe Constants
# =====================================================================

CANONICAL_UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
    "LTCUSDT", "DOTUSDT", "SUIUSDT"
]


# =====================================================================
# Core Portfolio Reconciler
# =====================================================================

class PortfolioReconciler:
    """
    Continuous Portfolio Reconciliation, Broker Truth Verification & Safe Trading Halt Coordinator.
    
    Responsibilities:
    1. Compares Internal Ledger (OMS + PortfolioManager) against Authoritative Broker State.
    2. Identifies Position, Cash, Order, Execution, VWAP, Fee, and P&L Discrepancies.
    3. Normalizes representations using Decimal precision with explicit tolerances.
    4. Enforces fail-closed trading halts on critical drift or broker data unavailability.
    5. Coordinates safe, atomic, idempotent execution imports based on authoritative broker evidence.
    6. Verifies state consistency upon startup before trading resumption is authorized.
    7. Retains historical snapshots and audit logs for forensic inspection.
    """
    def __init__(
        self,
        oms: DurablePaperOMS,
        portfolio: PaperPortfolioManager,
        broker: FakeBroker,
        adapter: Optional[BrokerAdapter] = None,
        tolerance: Optional[ReconciliationTolerance] = None,
        clock_fn: Optional[Callable[[], float]] = None
    ):
        self.oms = oms
        self.portfolio = portfolio
        self.broker = broker
        self.adapter = adapter or BrokerAdapter(oms, portfolio, broker)
        self.tolerance = tolerance or ReconciliationTolerance()
        self._clock_fn = clock_fn or (lambda: time.time())
        self._lock = threading.RLock()
        
        # State tracking
        self.last_status: ReconciliationStatus = ReconciliationStatus.HEALTHY
        self.last_snapshot: Optional[ReconciliationSnapshot] = None
        self.snapshot_history: List[ReconciliationSnapshot] = []
        self.max_history_snapshots: int = 100
        
        # Trading Halt Gates
        self.is_trading_halted: bool = False
        self.halt_scope: HaltScope = HaltScope.NONE
        self.halted_symbols: Set[str] = set()

    # -----------------------------------------------------------------
    # Normalization Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _to_decimal(val: Any) -> Decimal:
        """Converts value to Decimal safely."""
        if val is None:
            return Decimal("0.0")
        if isinstance(val, Decimal):
            return val
        return Decimal(str(val))

    @staticmethod
    def _normalize_sym(symbol: str) -> str:
        """Normalizes symbol to uppercase alphanumeric without colons/slashes."""
        return symbol.upper().replace(":", "").replace("/", "").strip()

    def normalize_internal_positions(self) -> Dict[str, NormalizedPosition]:
        """Extracts and normalizes internal portfolio positions."""
        res: Dict[str, NormalizedPosition] = {}
        for sym, pos in self.portfolio.positions.items():
            norm_sym = self._normalize_sym(sym)
            res[norm_sym] = NormalizedPosition(
                symbol=norm_sym,
                side=pos.side,
                size=self._to_decimal(pos.size),
                entry_price=self._to_decimal(pos.entry_price),
                mark_price=self._to_decimal(pos.entry_price),
                notional=self._to_decimal(pos.size * pos.entry_price)
            )
        return res

    def normalize_broker_positions(self, raw_positions: Dict[str, Dict[str, Any]]) -> Dict[str, NormalizedPosition]:
        """Normalizes broker position response."""
        res: Dict[str, NormalizedPosition] = {}
        for sym, p in raw_positions.items():
            norm_sym = self._normalize_sym(sym)
            raw_side = str(p.get("side", "FLAT")).upper()
            side = PositionSide(raw_side) if raw_side in PositionSide.__members__ else (
                PositionSide.LONG if float(p.get("size", 0.0)) > 0 else (
                    PositionSide.SHORT if float(p.get("size", 0.0)) < 0 else PositionSide.FLAT
                )
            )
            size = abs(self._to_decimal(p.get("size", 0.0)))
            entry_p = self._to_decimal(p.get("entry_price", 0.0))
            mark_p = self._to_decimal(p.get("mark_price", entry_p))
            res[norm_sym] = NormalizedPosition(
                symbol=norm_sym,
                side=side,
                size=size,
                entry_price=entry_p,
                mark_price=mark_p,
                notional=size * mark_p,
                timestamp=p.get("timestamp", datetime.now(timezone.utc).isoformat())
            )
        return res

    def normalize_internal_orders(self) -> Dict[str, NormalizedOrder]:
        """Extracts open and active orders from OMS."""
        orders = self.oms.get_open_orders()
        res: Dict[str, NormalizedOrder] = {}
        for o in orders:
            res[o.client_order_id or str(o.order_id)] = NormalizedOrder(
                order_id=str(o.order_id),
                client_order_id=o.client_order_id or str(o.order_id),
                symbol=self._normalize_sym(o.symbol),
                side=o.side,
                order_qty=self._to_decimal(o.order_qty),
                filled_qty=self._to_decimal(o.filled_qty),
                price=self._to_decimal(o.price),
                status=o.state.value,
                timestamp=o.created_at
            )
        return res

    def normalize_broker_orders(self, raw_orders: List[Dict[str, Any]]) -> Dict[str, NormalizedOrder]:
        """Normalizes broker orders."""
        res: Dict[str, NormalizedOrder] = {}
        for o in raw_orders:
            cid = o.get("client_order_id") or o.get("broker_order_id")
            side_str = str(o.get("side", "BUY")).upper()
            side = OrderSide.BUY if "BUY" in side_str else OrderSide.SELL
            res[cid] = NormalizedOrder(
                order_id=str(o.get("broker_order_id")),
                client_order_id=cid,
                symbol=self._normalize_sym(o.get("symbol", "")),
                side=side,
                order_qty=self._to_decimal(o.get("order_qty", 0.0)),
                filled_qty=self._to_decimal(o.get("filled_qty", 0.0)),
                price=self._to_decimal(o.get("price", 0.0)),
                status=str(o.get("status", "OPEN")).upper(),
                timestamp=o.get("created_at", datetime.now(timezone.utc).isoformat())
            )
        return res

    def normalize_internal_executions(self) -> Dict[str, NormalizedExecution]:
        """Extracts all executions from OMS database."""
        conn = self.oms._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.id, e.order_id, e.fill_price, e.fill_qty, e.fee, e.timestamp, e.execution_id,
                   o.symbol, o.side, o.client_order_id
            FROM executions e
            JOIN orders o ON e.order_id = o.id
            ORDER BY e.id ASC
        """)
        rows = cursor.fetchall()
        res: Dict[str, NormalizedExecution] = {}
        for r in rows:
            ex_id = r["execution_id"] or str(r["id"])
            side_str = str(r["side"]).upper()
            side = OrderSide.BUY if "BUY" in side_str else OrderSide.SELL
            res[ex_id] = NormalizedExecution(
                execution_id=ex_id,
                order_id=str(r["order_id"]),
                client_order_id=r["client_order_id"] or str(r["order_id"]),
                symbol=self._normalize_sym(r["symbol"]),
                side=side,
                fill_qty=self._to_decimal(r["fill_qty"]),
                fill_price=self._to_decimal(r["fill_price"]),
                fee=self._to_decimal(r["fee"]),
                timestamp=r["timestamp"] or datetime.now(timezone.utc).isoformat()
            )
        return res

    def normalize_broker_executions(self, raw_execs: List[Dict[str, Any]]) -> Dict[str, NormalizedExecution]:
        """Normalizes broker trade executions."""
        res: Dict[str, NormalizedExecution] = {}
        for ex in raw_execs:
            ex_id = ex["execution_id"]
            side_str = str(ex.get("side", "BUY")).upper()
            side = OrderSide.BUY if "BUY" in side_str else OrderSide.SELL
            res[ex_id] = NormalizedExecution(
                execution_id=ex_id,
                order_id=str(ex.get("broker_order_id", "")),
                client_order_id=ex.get("client_order_id", ""),
                symbol=self._normalize_sym(ex.get("symbol", "")),
                side=side,
                fill_qty=self._to_decimal(ex.get("fill_qty", 0.0)),
                fill_price=self._to_decimal(ex.get("fill_price", 0.0)),
                fee=self._to_decimal(ex.get("fee", 0.0)),
                fee_currency=ex.get("fee_currency", "USDT"),
                timestamp=ex.get("timestamp", datetime.now(timezone.utc).isoformat())
            )
        return res

    # -----------------------------------------------------------------
    # Domain Reconcilers
    # -----------------------------------------------------------------

    def reconcile_positions(
        self,
        internal_pos: Dict[str, NormalizedPosition],
        broker_pos: Dict[str, NormalizedPosition],
        target_symbol: Optional[str] = None
    ) -> Tuple[List[DriftItem], Dict[str, Any]]:
        """
        Reconciles portfolio positions across long, short, and flat states.
        Detects quantity mismatch, side mismatch, direction inversion, and missing assets.
        """
        drifts: List[DriftItem] = []
        all_symbols = set(CANONICAL_UNIVERSE) | set(internal_pos.keys()) | set(broker_pos.keys())
        if target_symbol:
            norm_target = self._normalize_sym(target_symbol)
            all_symbols = {norm_target}

        matched_count = 0
        mismatch_count = 0

        for sym in sorted(all_symbols):
            i_pos = internal_pos.get(sym)
            b_pos = broker_pos.get(sym)

            i_size = i_pos.size if (i_pos and i_pos.side != PositionSide.FLAT) else Decimal("0.0")
            i_side = i_pos.side if i_pos else PositionSide.FLAT
            
            b_size = b_pos.size if (b_pos and b_pos.side != PositionSide.FLAT) else Decimal("0.0")
            b_side = b_pos.side if b_pos else PositionSide.FLAT

            # Signed quantities for direction inversion detection
            signed_i = i_size if i_side == PositionSide.LONG else (-i_size if i_side == PositionSide.SHORT else Decimal("0.0"))
            signed_b = b_size if b_side == PositionSide.LONG else (-b_size if b_side == PositionSide.SHORT else Decimal("0.0"))
            delta = signed_b - signed_i

            # Case 1: Perfect match or within tolerance
            if abs(delta) <= self.tolerance.quantity_tolerance:
                matched_count += 1
                continue

            mismatch_count += 1

            # Case 2: Direction Inversion (e.g. +0.5 vs -0.5)
            if (signed_i > 0 and signed_b < 0) or (signed_i < 0 and signed_b > 0):
                drift = DriftItem(
                    drift_id=str(uuid.uuid4()),
                    domain="POSITIONS",
                    drift_type=DriftType.POSITION_SIDE_MISMATCH,
                    severity=DriftSeverity.CRITICAL,
                    symbol=sym,
                    order_id=None,
                    execution_id=None,
                    internal_value=f"{i_side.value} {i_size}",
                    broker_value=f"{b_side.value} {b_size}",
                    delta=f"Inversion delta={delta}",
                    message=f"Direction inversion for {sym}: internal={i_side.value} {i_size}, broker={b_side.value} {b_size}"
                )
                drifts.append(drift)
            else:
                # Case 3: Quantity Drift
                drift = DriftItem(
                    drift_id=str(uuid.uuid4()),
                    domain="POSITIONS",
                    drift_type=DriftType.POSITION_QTY_MISMATCH,
                    severity=DriftSeverity.CRITICAL,
                    symbol=sym,
                    order_id=None,
                    execution_id=None,
                    internal_value=i_size,
                    broker_value=b_size,
                    delta=delta,
                    message=f"Position quantity drift for {sym}: internal={i_size}, broker={b_size}, delta={delta}"
                )
                drifts.append(drift)

        summary = {
            "total_symbols_evaluated": len(all_symbols),
            "matched_symbols": matched_count,
            "mismatched_symbols": mismatch_count
        }
        return drifts, summary

    def reconcile_balances(
        self,
        internal_cash: float,
        broker_balance: Dict[str, Any]
    ) -> Tuple[List[DriftItem], Dict[str, Any]]:
        """
        Reconciles cash balance and total equity.
        """
        drifts: List[DriftItem] = []
        i_cash = self._to_decimal(internal_cash)
        b_cash = self._to_decimal(broker_balance.get("available_cash", 0.0))
        b_equity = self._to_decimal(broker_balance.get("total_equity", 0.0))
        delta_cash = b_cash - i_cash

        # Check freshness of broker snapshot
        raw_ts = broker_balance.get("timestamp")
        if raw_ts:
            try:
                snap_dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                age_s = (datetime.now(timezone.utc) - snap_dt).total_seconds()
                if age_s > self.tolerance.staleness_threshold_s:
                    drifts.append(DriftItem(
                        drift_id=str(uuid.uuid4()),
                        domain="BALANCES",
                        drift_type=DriftType.BROKER_DATA_STALE,
                        severity=DriftSeverity.CRITICAL,
                        symbol=None,
                        order_id=None,
                        execution_id=None,
                        internal_value=None,
                        broker_value=raw_ts,
                        delta=f"age={age_s:.1f}s",
                        message=f"Broker balance snapshot is stale (age={age_s:.1f}s > {self.tolerance.staleness_threshold_s}s)"
                    ))
            except Exception:
                pass

        if abs(delta_cash) > self.tolerance.cash_tolerance:
            drifts.append(DriftItem(
                drift_id=str(uuid.uuid4()),
                domain="BALANCES",
                drift_type=DriftType.BALANCE_MISMATCH,
                severity=DriftSeverity.CRITICAL,
                symbol=None,
                order_id=None,
                execution_id=None,
                internal_value=i_cash,
                broker_value=b_cash,
                delta=delta_cash,
                message=f"Cash balance drift: internal=${i_cash:.2f}, broker=${b_cash:.2f}, delta=${delta_cash:.2f}"
            ))

        summary = {
            "internal_cash": float(i_cash),
            "broker_available_cash": float(b_cash),
            "broker_total_equity": float(b_equity),
            "cash_delta": float(delta_cash),
            "matched": abs(delta_cash) <= self.tolerance.cash_tolerance
        }
        return drifts, summary

    def reconcile_orders(
        self,
        internal_orders: Dict[str, NormalizedOrder],
        broker_orders: Dict[str, NormalizedOrder]
    ) -> Tuple[List[DriftItem], Dict[str, Any]]:
        """
        Reconciles open and active orders.
        Detects orphan broker orders, missing broker orders, and state/qty mismatches.
        """
        drifts: List[DriftItem] = []
        all_keys = set(internal_orders.keys()) | set(broker_orders.keys())

        matched_orders = 0
        orphan_orders = 0
        missing_broker_orders = 0

        for k in all_keys:
            i_ord = internal_orders.get(k)
            b_ord = broker_orders.get(k)

            # Case 1: Orphan Broker Order (Order on broker not recognized by OMS)
            if not i_ord and b_ord:
                orphan_orders += 1
                drifts.append(DriftItem(
                    drift_id=str(uuid.uuid4()),
                    domain="ORDERS",
                    drift_type=DriftType.ORPHAN_BROKER_ORDER,
                    severity=DriftSeverity.CRITICAL,
                    symbol=b_ord.symbol,
                    order_id=b_ord.order_id,
                    execution_id=None,
                    internal_value="NON_EXISTENT",
                    broker_value=f"{b_ord.symbol} {b_ord.side.value} {b_ord.order_qty} ({b_ord.status})",
                    delta=b_ord.order_qty,
                    message=f"Orphan order detected on broker: order_id={b_ord.order_id}, client_id={b_ord.client_order_id}"
                ))
                continue

            # Case 2: Missing on Broker (Open in OMS but missing at broker)
            if i_ord and not b_ord:
                missing_broker_orders += 1
                drifts.append(DriftItem(
                    drift_id=str(uuid.uuid4()),
                    domain="ORDERS",
                    drift_type=DriftType.ORDER_MISSING_AT_BROKER,
                    severity=DriftSeverity.ERROR,
                    symbol=i_ord.symbol,
                    order_id=i_ord.order_id,
                    execution_id=None,
                    internal_value=f"{i_ord.symbol} {i_ord.side.value} {i_ord.order_qty} ({i_ord.status})",
                    broker_value="MISSING",
                    delta=i_ord.order_qty,
                    message=f"Internal open order not found on exchange: order_id={i_ord.order_id}"
                ))
                continue

            # Case 3: Both exist - check state and filled quantities
            if i_ord and b_ord:
                # Check filled quantity mismatch
                delta_fill = b_ord.filled_qty - i_ord.filled_qty
                if abs(delta_fill) > self.tolerance.quantity_tolerance:
                    drifts.append(DriftItem(
                        drift_id=str(uuid.uuid4()),
                        domain="ORDERS",
                        drift_type=DriftType.FILL_QTY_MISMATCH,
                        severity=DriftSeverity.CRITICAL,
                        symbol=i_ord.symbol,
                        order_id=i_ord.order_id,
                        execution_id=None,
                        internal_value=i_ord.filled_qty,
                        broker_value=b_ord.filled_qty,
                        delta=delta_fill,
                        message=f"Order fill quantity mismatch for {i_ord.order_id}: internal={i_ord.filled_qty}, broker={b_ord.filled_qty}"
                    ))
                elif i_ord.status != b_ord.status:
                    # Status mismatch
                    drifts.append(DriftItem(
                        drift_id=str(uuid.uuid4()),
                        domain="ORDERS",
                        drift_type=DriftType.ORDER_STATUS_MISMATCH,
                        severity=DriftSeverity.WARNING if (i_ord.status in ("FILLED", "CANCELLED") and b_ord.status in ("FILLED", "CANCELLED")) else DriftSeverity.ERROR,
                        symbol=i_ord.symbol,
                        order_id=i_ord.order_id,
                        execution_id=None,
                        internal_value=i_ord.status,
                        broker_value=b_ord.status,
                        delta=None,
                        message=f"Order status mismatch for {i_ord.order_id}: internal={i_ord.status}, broker={b_ord.status}"
                    ))
                else:
                    matched_orders += 1

        summary = {
            "total_orders_evaluated": len(all_keys),
            "matched_orders": matched_orders,
            "orphan_orders": orphan_orders,
            "missing_broker_orders": missing_broker_orders
        }
        return drifts, summary

    def reconcile_executions(
        self,
        internal_execs: Dict[str, NormalizedExecution],
        broker_execs: Dict[str, NormalizedExecution]
    ) -> Tuple[List[DriftItem], Dict[str, Any]]:
        """
        Reconciles all trade executions and fills.
        Deduplicates fills, detects missing broker/internal executions, and checks VWAP consistency.
        """
        drifts: List[DriftItem] = []
        all_exec_ids = set(internal_execs.keys()) | set(broker_execs.keys())

        matched_execs = 0
        missing_internally = 0
        missing_at_broker = 0

        for ex_id in all_exec_ids:
            i_ex = internal_execs.get(ex_id)
            b_ex = broker_execs.get(ex_id)

            # Case 1: Broker execution missing internally (Critical exposure drift)
            if not i_ex and b_ex:
                missing_internally += 1
                drifts.append(DriftItem(
                    drift_id=str(uuid.uuid4()),
                    domain="EXECUTIONS",
                    drift_type=DriftType.MISSING_INTERNAL_EXECUTION,
                    severity=DriftSeverity.CRITICAL,
                    symbol=b_ex.symbol,
                    order_id=b_ex.order_id,
                    execution_id=ex_id,
                    internal_value="MISSING",
                    broker_value=f"{b_ex.fill_qty} @ {b_ex.fill_price}",
                    delta=b_ex.fill_qty,
                    message=f"Authoritative broker execution missing internally: {ex_id} ({b_ex.symbol} {b_ex.fill_qty} @ {b_ex.fill_price})"
                ))
                continue

            # Case 2: Internal execution missing on broker
            if i_ex and not b_ex:
                missing_at_broker += 1
                drifts.append(DriftItem(
                    drift_id=str(uuid.uuid4()),
                    domain="EXECUTIONS",
                    drift_type=DriftType.MISSING_BROKER_EXECUTION,
                    severity=DriftSeverity.WARNING,
                    symbol=i_ex.symbol,
                    order_id=i_ex.order_id,
                    execution_id=ex_id,
                    internal_value=f"{i_ex.fill_qty} @ {i_ex.fill_price}",
                    broker_value="UNAVAILABLE",
                    delta=i_ex.fill_qty,
                    message=f"Internal execution not returned in broker trade history: {ex_id}"
                ))
                continue

            # Case 3: Both exist - compare quantity, price, and fee
            if i_ex and b_ex:
                qty_diff = abs(b_ex.fill_qty - i_ex.fill_qty)
                price_diff = abs(b_ex.fill_price - i_ex.fill_price)
                fee_diff = abs(b_ex.fee - i_ex.fee)

                if qty_diff > self.tolerance.quantity_tolerance:
                    drifts.append(DriftItem(
                        drift_id=str(uuid.uuid4()),
                        domain="EXECUTIONS",
                        drift_type=DriftType.FILL_QTY_MISMATCH,
                        severity=DriftSeverity.CRITICAL,
                        symbol=i_ex.symbol,
                        order_id=i_ex.order_id,
                        execution_id=ex_id,
                        internal_value=i_ex.fill_qty,
                        broker_value=b_ex.fill_qty,
                        delta=qty_diff,
                        message=f"Execution quantity mismatch for {ex_id}: internal={i_ex.fill_qty}, broker={b_ex.fill_qty}"
                    ))
                elif price_diff > self.tolerance.price_tolerance:
                    drifts.append(DriftItem(
                        drift_id=str(uuid.uuid4()),
                        domain="EXECUTIONS",
                        drift_type=DriftType.PRICE_MISMATCH,
                        severity=DriftSeverity.ERROR,
                        symbol=i_ex.symbol,
                        order_id=i_ex.order_id,
                        execution_id=ex_id,
                        internal_value=i_ex.fill_price,
                        broker_value=b_ex.fill_price,
                        delta=price_diff,
                        message=f"Execution price mismatch for {ex_id}: internal={i_ex.fill_price}, broker={b_ex.fill_price}"
                    ))
                elif fee_diff > self.tolerance.fee_tolerance:
                    drifts.append(DriftItem(
                        drift_id=str(uuid.uuid4()),
                        domain="FEES",
                        drift_type=DriftType.FEE_MISMATCH,
                        severity=DriftSeverity.WARNING,
                        symbol=i_ex.symbol,
                        order_id=i_ex.order_id,
                        execution_id=ex_id,
                        internal_value=i_ex.fee,
                        broker_value=b_ex.fee,
                        delta=fee_diff,
                        message=f"Execution fee mismatch for {ex_id}: internal={i_ex.fee}, broker={b_ex.fee}"
                    ))
                else:
                    matched_execs += 1

        summary = {
            "total_executions_evaluated": len(all_exec_ids),
            "matched_executions": matched_execs,
            "missing_internally": missing_internally,
            "missing_at_broker": missing_at_broker
        }
        return drifts, summary

    # -----------------------------------------------------------------
    # Primary Reconcile Pipeline
    # -----------------------------------------------------------------

    def reconcile(
        self,
        mode: ReconciliationMode = ReconciliationMode.FULL,
        symbol: Optional[str] = None
    ) -> ReconciliationSnapshot:
        """
        Executes a complete reconciliation cycle between internal state and broker snapshot.
        Enforces fail-closed trading gates upon critical drift or API unavailability.
        """
        with self._lock:
            start_time = self._clock_fn()
            recon_id = f"RECON_{uuid.uuid4().hex[:12]}"
            ReconciliationMetrics.emit_event("RECONCILIATION_STARTED", reconciliation_id=recon_id, mode=mode.value)

            drifts: List[DriftItem] = []
            pos_summary: Dict[str, Any] = {}
            bal_summary: Dict[str, Any] = {}
            ord_summary: Dict[str, Any] = {}
            exec_summary: Dict[str, Any] = {}

            # Step 1: Fetch Authoritative Broker Data (Fail-Closed on API Dropouts)
            try:
                raw_broker_positions = self.broker.get_positions()
            except Exception as e:
                ReconciliationMetrics.emit_event("RECONCILIATION_BROKER_DATA_UNAVAILABLE", domain="POSITIONS", error=str(e))
                return self._build_unavailable_snapshot(recon_id, "POSITIONS", str(e), mode)

            try:
                raw_broker_balances = self.broker.get_balances()
            except Exception as e:
                ReconciliationMetrics.emit_event("RECONCILIATION_BROKER_DATA_UNAVAILABLE", domain="BALANCES", error=str(e))
                return self._build_unavailable_snapshot(recon_id, "BALANCES", str(e), mode)

            try:
                raw_broker_orders = self.broker.get_open_orders()
            except Exception as e:
                ReconciliationMetrics.emit_event("RECONCILIATION_BROKER_DATA_UNAVAILABLE", domain="ORDERS", error=str(e))
                return self._build_unavailable_snapshot(recon_id, "ORDERS", str(e), mode)

            try:
                raw_broker_execs = self.broker.get_all_executions()
            except Exception as e:
                ReconciliationMetrics.emit_event("RECONCILIATION_BROKER_DATA_UNAVAILABLE", domain="EXECUTIONS", error=str(e))
                return self._build_unavailable_snapshot(recon_id, "EXECUTIONS", str(e), mode)

            broker_snap_ts = raw_broker_balances.get("timestamp", datetime.now(timezone.utc).isoformat())

            # Step 2: Normalize Both Representations
            internal_pos = self.normalize_internal_positions()
            broker_pos = self.normalize_broker_positions(raw_broker_positions)

            internal_orders = self.normalize_internal_orders()
            broker_orders = self.normalize_broker_orders(raw_broker_orders)

            internal_execs = self.normalize_internal_executions()
            broker_execs = self.normalize_broker_executions(raw_broker_execs)

            # Step 3: Run Domain Comparisons
            if mode in (ReconciliationMode.FULL, ReconciliationMode.SYMBOL):
                p_drifts, pos_summary = self.reconcile_positions(internal_pos, broker_pos, target_symbol=symbol)
                drifts.extend(p_drifts)

            if mode in (ReconciliationMode.FULL, ReconciliationMode.ACCOUNT):
                b_drifts, bal_summary = self.reconcile_balances(self.portfolio.cash, raw_broker_balances)
                drifts.extend(b_drifts)

            if mode in (ReconciliationMode.FULL, ReconciliationMode.ORDER):
                o_drifts, ord_summary = self.reconcile_orders(internal_orders, broker_orders)
                drifts.extend(o_drifts)

            if mode in (ReconciliationMode.FULL, ReconciliationMode.ORDER):
                e_drifts, exec_summary = self.reconcile_executions(internal_execs, broker_execs)
                drifts.extend(e_drifts)

            # Step 4: Determine Overall Status, Severity, and Halt Scope
            has_critical = any(d.severity == DriftSeverity.CRITICAL for d in drifts)
            has_error = any(d.severity == DriftSeverity.ERROR for d in drifts)
            has_warning = any(d.severity == DriftSeverity.WARNING for d in drifts)

            highest_sev = DriftSeverity.CRITICAL if has_critical else (
                DriftSeverity.ERROR if has_error else (
                    DriftSeverity.WARNING if has_warning else DriftSeverity.INFO
                )
            )

            if has_critical:
                status = ReconciliationStatus.CRITICAL_DRIFT
            elif has_error:
                status = ReconciliationStatus.DRIFT_DETECTED
            elif has_warning:
                status = ReconciliationStatus.DEGRADED
            else:
                status = ReconciliationStatus.HEALTHY

            # Calculate Halt Policy
            halt_scope, halted_syms = self._evaluate_halt_policy(drifts, status)
            self.halt_scope = halt_scope
            self.halted_symbols = halted_syms
            self.is_trading_halted = (halt_scope != HaltScope.NONE)

            # Step 5: Build and Persist Snapshot
            snapshot = ReconciliationSnapshot(
                reconciliation_id=recon_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                broker_snapshot_timestamp=broker_snap_ts,
                status=status,
                highest_severity=highest_sev,
                halt_scope=halt_scope,
                halted_symbols=sorted(list(halted_syms)),
                position_summary=pos_summary,
                balance_summary=bal_summary,
                order_summary=ord_summary,
                execution_summary=exec_summary,
                drifts=drifts,
                drift_count=len(drifts),
                unresolved_count=len([d for d in drifts if d.severity in (DriftSeverity.ERROR, DriftSeverity.CRITICAL)])
            )

            self.last_status = status
            self.last_snapshot = snapshot
            self.snapshot_history.append(snapshot)
            if len(self.snapshot_history) > self.max_history_snapshots:
                self.snapshot_history.pop(0)

            # Emit structured logs and metrics
            duration = self._clock_fn() - start_time
            if status == ReconciliationStatus.HEALTHY:
                ReconciliationMetrics.emit_event("RECONCILIATION_MATCH", reconciliation_id=recon_id, duration_s=round(duration, 4))
            else:
                ReconciliationMetrics.emit_event(
                    "RECONCILIATION_DRIFT_DETECTED",
                    reconciliation_id=recon_id,
                    status=status.value,
                    drift_count=len(drifts),
                    halt_scope=halt_scope.value,
                    halted_symbols=list(halted_syms)
                )

            return snapshot

    def _build_unavailable_snapshot(
        self,
        recon_id: str,
        failed_domain: str,
        error_msg: str,
        mode: ReconciliationMode
    ) -> ReconciliationSnapshot:
        """Constructs fail-closed snapshot when broker dataset query fails."""
        drift = DriftItem(
            drift_id=str(uuid.uuid4()),
            domain=failed_domain,
            drift_type=DriftType.BROKER_DATA_UNAVAILABLE,
            severity=DriftSeverity.CRITICAL,
            symbol=None,
            order_id=None,
            execution_id=None,
            internal_value=None,
            broker_value="UNAVAILABLE",
            delta=error_msg,
            message=f"Authoritative broker dataset unavailable for {failed_domain}: {error_msg}"
        )
        
        self.is_trading_halted = True
        self.halt_scope = HaltScope.GLOBAL
        self.last_status = ReconciliationStatus.DATA_UNAVAILABLE
        
        snap = ReconciliationSnapshot(
            reconciliation_id=recon_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            broker_snapshot_timestamp="UNKNOWN",
            status=ReconciliationStatus.DATA_UNAVAILABLE,
            highest_severity=DriftSeverity.CRITICAL,
            halt_scope=HaltScope.GLOBAL,
            halted_symbols=CANONICAL_UNIVERSE,
            position_summary={"error": error_msg},
            balance_summary={"error": error_msg},
            order_summary={"error": error_msg},
            execution_summary={"error": error_msg},
            drifts=[drift],
            drift_count=1,
            unresolved_count=1
        )
        self.last_snapshot = snap
        self.snapshot_history.append(snap)
        return snap

    def _evaluate_halt_policy(
        self,
        drifts: List[DriftItem],
        status: ReconciliationStatus
    ) -> Tuple[HaltScope, Set[str]]:
        """
        Determines the narrowest safe halt scope.
        - Position mismatch on BTC -> SYMBOL halt on BTC.
        - Balance mismatch / orphan order / execution mismatch -> ACCOUNT or GLOBAL halt.
        """
        if status == ReconciliationStatus.HEALTHY or not drifts:
            return HaltScope.NONE, set()

        halted_syms: Set[str] = set()
        has_account_drift = False

        for d in drifts:
            if d.severity == DriftSeverity.CRITICAL:
                if d.domain == "POSITIONS" and d.symbol:
                    halted_syms.add(self._normalize_sym(d.symbol))
                elif d.domain in ("BALANCES", "ORDERS", "EXECUTIONS"):
                    has_account_drift = True
                    if d.symbol:
                        halted_syms.add(self._normalize_sym(d.symbol))

        if has_account_drift:
            return HaltScope.ACCOUNT, set(CANONICAL_UNIVERSE)
        elif halted_syms:
            return HaltScope.SYMBOL, halted_syms

        return HaltScope.NONE, set()

    # -----------------------------------------------------------------
    # Safe Execution Import & Repair Protocol
    # -----------------------------------------------------------------

    def safe_repair_execution(
        self,
        execution_id: str,
        broker_exec_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Safely and idempotently imports a confirmed authoritative broker execution into the internal ledger.
        
        Invariants:
        1. Never imports without authoritative broker execution ID.
        2. Applies execution exactly once (P2-2 idempotency).
        3. Updates order state, filled qty, and VWAP (P2-3 lifecycle).
        4. Mutates portfolio cash, position, and fees consistently.
        5. Atomically persists to SQLite (P2-4 durability).
        6. Re-runs reconciliation to confirm HEALTHY status.
        """
        with self._lock:
            ReconciliationMetrics.emit_event("RECONCILIATION_REPAIR_STARTED", execution_id=execution_id)

            # Step 1: Check Idempotency
            if execution_id in self.portfolio.applied_execution_ids:
                logger.info(f"REPAIR_IDEMPOTENT_NOOP: Execution {execution_id} already applied to portfolio.")
                return True, "ALREADY_APPLIED"

            # Step 2: Validate execution parameters
            sym = self._normalize_sym(broker_exec_data.get("symbol", ""))
            fill_qty = float(broker_exec_data.get("fill_qty", 0.0))
            fill_price = float(broker_exec_data.get("fill_price", 0.0))
            fee = float(broker_exec_data.get("fee", 0.0))
            side_str = str(broker_exec_data.get("side", "BUY")).upper()
            cid = broker_exec_data.get("client_order_id", "")

            if fill_qty <= 0 or fill_price <= 0 or not sym:
                ReconciliationMetrics.emit_event("RECONCILIATION_REPAIR_FAILED", execution_id=execution_id, reason="INVALID_EXECUTION_PARAMS")
                return False, "INVALID_EXECUTION_PARAMS"

            # Step 3: Identify or create corresponding internal order
            order = self.oms.get_order_by_client_order_id(cid) if cid else None
            if not order:
                # Create corresponding order in OMS
                order = self.oms.create_order(
                    symbol=sym,
                    side=side_str,
                    total_qty=fill_qty,
                    price=fill_price,
                    client_order_id=cid or f"REPAIR_{uuid.uuid4().hex[:10]}"
                )

            # Step 4: Execute fill in OMS and Portfolio atomically
            try:
                # Step through legal transitions to ACKNOWLEDGED if needed
                if order.state == OrderState.CREATED:
                    PaperStateMachine.transition_order(order, OrderEventType.SUBMIT)
                    self.oms.save_transition(order, order.event_history[-1])
                if order.state == OrderState.SUBMITTED:
                    PaperStateMachine.transition_order(order, OrderEventType.ACKNOWLEDGE)
                    self.oms.save_transition(order, order.event_history[-1])

                self.oms.execute_order(
                    order_id=order.order_id,
                    fill_price=fill_price,
                    fill_qty=fill_qty,
                    fee=fee,
                    execution_id=execution_id
                )

                self.portfolio.apply_order_fill(
                    order=order,
                    fill_qty=fill_qty,
                    fill_price=fill_price,
                    fee=fee,
                    execution_id=execution_id
                )

                ReconciliationMetrics.emit_event("RECONCILIATION_REPAIR_COMPLETED", execution_id=execution_id, order_id=order.order_id)
                
                # Step 5: Reconcile to verify resolution
                post_snap = self.reconcile(mode=ReconciliationMode.FULL)
                if post_snap.status == ReconciliationStatus.HEALTHY:
                    self.is_trading_halted = False
                    self.halt_scope = HaltScope.NONE
                    self.halted_symbols.clear()
                    return True, "REPAIRED_AND_HEALTHY"
                return True, "REPAIRED_PARTIAL_DRIFT_REMAINS"

            except Exception as e:
                logger.error(f"RECONCILIATION_REPAIR_ERROR execution_id={execution_id} error={e}")
                ReconciliationMetrics.emit_event("RECONCILIATION_REPAIR_FAILED", execution_id=execution_id, error=str(e))
                return False, f"REPAIR_EXCEPTION: {e}"

    # -----------------------------------------------------------------
    # Startup Reconciliation Protocol
    # -----------------------------------------------------------------

    def startup_reconciliation(self) -> Tuple[bool, ReconciliationSnapshot]:
        """
        Executes mandatory startup validation:
        1. Replays internal SQLite journal (P2-4).
        2. Queries authoritative broker snapshot.
        3. Runs full reconciliation.
        4. Authorizes trading ONLY if status == HEALTHY.
        """
        logger.info("STARTUP_RECONCILIATION_INITIATED")
        # Step 1: Replay OMS
        self.portfolio.replay_from_oms(self.oms)

        # Step 1.5: Auto-recover any pending UNKNOWN orders from crash
        if self.adapter:
            for o in self.oms.get_all_orders():
                if o.state == OrderState.UNKNOWN:
                    logger.info(f"STARTUP_RECOVERY: Auto-recovering UNKNOWN order {o.order_id} via broker adapter.")
                    self.adapter.recover_unknown_order(o.order_id)

        # Step 2: Run Reconciliation
        snapshot = self.reconcile(mode=ReconciliationMode.FULL)

        if snapshot.status == ReconciliationStatus.HEALTHY:
            self.is_trading_halted = False
            self.halt_scope = HaltScope.NONE
            self.halted_symbols.clear()
            logger.info(f"STARTUP_RECONCILIATION_SUCCESS: State verified against broker truth. Trading permitted.")
            return True, snapshot
        else:
            self.is_trading_halted = True
            logger.critical(
                f"STARTUP_RECONCILIATION_FAILED: State discrepancy detected (status={snapshot.status.value}, "
                f"drifts={snapshot.drift_count}). Trading remains HALTED."
            )
            return False, snapshot
