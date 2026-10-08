# P2-7 — Continuous Portfolio Reconciliation, Broker Truth Verification & Safe Trading Halt

## 1. Executive Summary

P2-7 establishes a continuous operational integrity subsystem that compares internal OMS/portfolio ledger state against authoritative broker reality. In high-stakes quantitative execution, distributed state divergence between an internal OMS and external exchange can arise from post-send network drops, unhandled partial fills, exchange fee discrepancies, manual account actions, exchange-side liquidations, or internal ledger corruptions.

The foundational invariant of P2-7 is:
$$\text{INTERNAL STATE MUST EITHER MATCH AUTHORITATIVE BROKER STATE OR TRADING MUST BE SAFELY HALTED.}$$

P2-7 enforces fail-closed execution semantics:
- Never silently accept unexplained divergence.
- Never guess or overwrite internal history without authoritative broker evidence.
- Never report a healthy status when broker endpoints time out.
- Support safe, atomic, idempotent execution imports based on exchange truth.

---

## 2. Why P2-7 Exists

In previous milestones:
- **P2-1**: Defined explicit order states, invariants, and transitions.
- **P2-2**: Guaranteed logical request idempotency and duplicate fill suppression.
- **P2-3**: Managed partial fills, multi-execution VWAP, and overfill protection.
- **P2-4**: Built write-ahead SQLite event journaling and deterministic crash replay.
- **P2-5**: Implemented fail-closed WebSocket heartbeat monitoring and stale data detection.
- **P2-6**: Handled broker timeouts, network failure classification, and `UNKNOWN` order recovery.

However, a fundamental distributed systems problem remained:
```
Internal Ledger (OMS State) <───────── RECONCILIATION ─────────> Authoritative Exchange State
   [ BTC = +0.50 ]                                                 [ BTC = +0.60 ]
   [ Cash = $10,000 ]                                              [ Cash = $9,400 ]
```
P2-7 continuously answers: *"Does our internal state agree with broker economic reality?"*

---

## 3. Authority Model

| System Domain | Authoritative System | Rationale |
|---|---|---|
| **Cash Balances** | **Broker / Exchange** | Realized funds, collateral, margin, and physical cash balances reside on the exchange. |
| **Asset Positions** | **Broker / Exchange** | Physical open contracts and token balances held at the custody/exchange layer. |
| **Exchange Orders** | **Broker / Exchange** | Active matching engine limit orders, book queues, and exchange order statuses. |
| **Trade Executions** | **Broker / Exchange** | Executed trade fills, fill prices, match timestamps, and transaction fees charged. |
| **Logical Order Intent** | **Internal OMS** | Strategy intent, signal timestamps, alpha models, risk limit allocations. |
| **Audit Event Journal** | **Internal OMS** | Immutable write-ahead transition history, attempt counts, and system forensic logs. |

The broker is the sole authority for **economic truth**. The internal OMS is the authority for **business intent and audit history**.

---

## 4. Existing Architecture

Audit of the repository confirmed the end-to-end operational flow:
```
Market Data Stream
       │
       ▼
P2-5 Health Gate (Heartbeat / Stale Detector)
       │
       ▼
Strategy Sizing & Risk Management (Frozen)
       │
       ▼
DurablePaperOMS (P2-1 Lifecycle, P2-4 SQLite Journal)
       │
       ▼
BrokerAdapter (P2-6 Fault Boundary)
       │
       ▼
Exchange / FakeBroker
       ▲
       │
PortfolioReconciler (P2-7 Continuous Loop & Startup Gate)
```

The [PortfolioReconciler](file:///c:/Users/ajayg/ai_crypto_bot/reconciliation/portfolio_reconciler.py) connects to `DurablePaperOMS`, `PaperPortfolioManager`, and `BrokerAdapter`/`FakeBroker`, performing periodic or event-triggered verification.

---

## 5. Internal State Model

The internal state is maintained via:
1. `DurablePaperOMS`: SQLite-backed order journal (`orders`, `executions`, `order_events`).
2. `PaperPortfolioManager`: In-memory cash balance, position inventory (`positions[symbol]`), and `applied_execution_ids` set.
3. State Replay: `replay_from_oms()` reconstructs portfolio balances from scratch by replaying the SQLite execution ledger.

---

## 6. Broker State Model

The broker state is queried via:
1. `get_positions()`: Symbol, side (`LONG`, `SHORT`, `FLAT`), size, entry price, mark price.
2. `get_balances()`: Available cash, total equity, currency (`USDT`), snapshot timestamp.
3. `get_open_orders()`: Active limit/stop orders on the exchange book.
4. `get_all_executions()`: List of all matched trades with `execution_id`, `fill_qty`, `fill_price`, `fee`.

---

## 7. Normalization Layer

To prevent floating-point inequality bugs:
- Quantities, prices, cash, and fees are converted to Python `Decimal`.
- Symbols are sanitized to uppercase alphanumeric strings (`BTCUSDT`).
- Positions are normalized into `NormalizedPosition`.
- Balances are normalized into `NormalizedBalance`.
- Orders and Executions are normalized into `NormalizedOrder` and `NormalizedExecution`.

---

## 8. Tolerances Model

| Parameter | Value | Rationale |
|---|---|---|
| `quantity_tolerance` | `0.000001` ($10^{-6}$) | Prevents false alerts on sub-satoshi crypto rounding artifacts. |
| `cash_tolerance` | `$0.01` | Allows for fractional cent currency rounding. |
| `price_tolerance` | `$0.0001` | Allows for $0.01\text{ bps}$ price discrepancy. |
| `fee_tolerance` | `$0.001` | Accommodates multi-tier exchange fee rounding. |
| `pnl_tolerance` | `$0.05` | Tolerates slight Mark-to-Market vs Realized timing nuances. |
| `staleness_threshold_s` | `60.0s` | Maximum allowable age of broker balance snapshot before flag. |

---

## 9. Position Reconciliation

For every asset in the 13-asset universe:
$$\Delta_{\text{qty}} = \text{signed\_broker\_qty} - \text{signed\_internal\_qty}$$
- **MATCH**: $|\Delta_{\text{qty}}| \le \text{tolerance}$.
- **POSITION_QTY_MISMATCH**: $|\Delta_{\text{qty}}| > \text{tolerance} \implies \text{CRITICAL}$.
- **POSITION_SIDE_MISMATCH**: Direction inversion (e.g. $+0.5\text{ BTC}$ vs $-0.5\text{ BTC}$) $\implies \text{CRITICAL}$.

---

## 10. Balance Reconciliation

Compares internal available cash against broker available cash:
$$\Delta_{\text{cash}} = \text{broker\_cash} - \text{internal\_cash}$$
- If $|\Delta_{\text{cash}}| > \text{cash\_tolerance} \implies \text{BALANCE\_MISMATCH}\ (\text{CRITICAL})$.
- Engages `ACCOUNT` halt scope, preventing new orders across all strategies.

---

## 11. Order Reconciliation

Compares internal open orders against exchange open orders:
1. **Orphan Broker Order**: Order exists on broker but absent from OMS $\implies \text{CRITICAL}$ (untracked open risk).
2. **Missing Broker Order**: Order open in OMS but missing on exchange $\implies \text{ERROR}$ (may have filled or expired).
3. **Status / Fill Mismatch**: Internal filled quantity differs from broker filled quantity $\implies \text{CRITICAL}$.

---

## 12. Execution Reconciliation

For every trade execution:
- Deduplicates fills by `execution_id`.
- **MISSING_INTERNAL_EXECUTION**: Broker executed trade absent internally $\implies \text{CRITICAL}$.
- **MISSING_BROKER_EXECUTION**: Internal execution not found in broker history $\implies \text{WARNING}$.
- Reconciles cumulative fill quantities and individual trade prices.

---

## 13. Fee Reconciliation

- Compares broker transaction fees against internal recorded fees per execution.
- If fee difference exceeds `fee_tolerance`, flags `FEE_MISMATCH` ($\text{WARNING}$).

---

## 14. P&L Reconciliation

- **Mark-to-Market vs Realized P&L**: Internal OMS tracks execution-based realized P&L, whereas exchange dashboards often display unrealized mark-to-market equity.
- The reconciler reports `MATCH` when realized P&L aligns and notes expected semantic differences for unrealized mark-to-market equity.

---

## 15. Drift Classification

| Drift Code | Domain | Severity | Fail-Closed Trigger |
|---|---|---|---|
| `POSITION_QTY_MISMATCH` | Positions | **CRITICAL** | Halts affected symbol |
| `POSITION_SIDE_MISMATCH` | Positions | **CRITICAL** | Halts affected symbol |
| `BALANCE_MISMATCH` | Balances | **CRITICAL** | Halts entire account |
| `ORPHAN_BROKER_ORDER` | Orders | **CRITICAL** | Halts affected symbol / account |
| `MISSING_INTERNAL_EXECUTION`| Executions | **CRITICAL** | Halts symbol until repaired |
| `FILL_QTY_MISMATCH` | Orders / Executions | **CRITICAL** | Halts affected symbol |
| `ORDER_MISSING_AT_BROKER` | Orders | **ERROR** | Triggers status query retry |
| `ORDER_STATUS_MISMATCH` | Orders | **ERROR** | Triggers order recovery |
| `PRICE_MISMATCH` | Executions | **ERROR** | Audit flag |
| `BROKER_DATA_UNAVAILABLE` | All | **CRITICAL** | Global trading halt |
| `BROKER_DATA_STALE` | Balances | **CRITICAL** | Global trading halt |

---

## 16. Severity Model

- `INFO`: Benign timing or metadata distinction.
- `WARNING`: Small tolerated difference or expected accounting difference.
- `ERROR`: State mismatch requiring query retry or investigation.
- `CRITICAL`: Mismatch capable of creating unintended market exposure.

---

## 17. Safety & Halt Policy

- `HaltScope.NONE`: Reconciliation 100% healthy; trading permitted.
- `HaltScope.SYMBOL`: Position mismatch on specific asset $\to$ halts trading for that symbol only.
- `HaltScope.ACCOUNT`: Cash or balance mismatch $\to$ halts all trading on the account.
- `HaltScope.GLOBAL`: Broker API unavailable or database failure $\to$ halts entire trading system.

---

## 18. Automatic Repair Policy

The reconciler follows strict evidence-based repair:
$$\text{DETECT} \implies \text{VERIFY} \implies \text{REPAIR ONLY WITH AUTHORITATIVE EVIDENCE} \implies \text{RECONCILE AGAIN}$$

### Allowed Repairs:
- **Authoritative Execution Import**: If broker returns confirmed `execution_id` with valid `fill_qty`, `fill_price`, and `fee`, `safe_repair_execution` atomically commits the fill to SQLite, transitions the order, and updates portfolio cash/position.

### Prohibited Repairs:
- Blindly setting internal cash = broker cash.
- Blindly setting internal position = broker position.
- Deleting internal audit events or executions.

---

## 19. P2-6 UNKNOWN Order Integration

When an order is in `OrderState.UNKNOWN` following a post-send network dropout:
- Reconciler queries broker status.
- If broker status is `FILLED`, resolves order and imports execution.
- If broker status is `REJECTED`, resolves rejection with zero portfolio drift.
- If broker status is `CANCELLED`, resolves cancellation.

---

## 20. Crash Recovery Integration

Upon process startup (P2-4):
1. SQLite PRAGMA integrity check.
2. Replay execution ledger from `oms.db`.
3. Query authoritative broker snapshot.
4. Execute `startup_reconciliation()`.
5. **Resume trading ONLY if status == HEALTHY**. If drift is detected, remain halted.

---

## 21. Continuous Reconciliation Loop

- Configurable periodic interval (e.g. every 60s).
- Event-triggered reconciliation:
  - On order timeout.
  - On UNKNOWN order creation.
  - On WebSocket reconnect.
  - On process startup.

---

## 22. Startup Reconciliation

Guarantees that an application never resumes automated trading merely because internal SQLite replay succeeded:
$$\text{Replay Success} \land \text{Broker Snapshot Match} \implies \text{Trading Permitted}$$

---

## 23. Observability & Structured Logging

### Prometheus Metrics Bridge
- `reconciliation_runs_total`: Counter by mode.
- `reconciliation_success_total`: Counter for MATCH cycles.
- `reconciliation_failure_total`: Counter for drift cycles.
- `reconciliation_drift_total`: Counter by domain and severity.
- `position_mismatch_total`, `balance_mismatch_total`, `order_mismatch_total`, `execution_mismatch_total`.
- `orphan_order_total`, `missing_execution_total`.
- `reconciliation_repairs_total`: Counter for successful repairs.
- `reconciliation_halts_total`: Counter by halt scope.

---

## 24. Test Matrix Summary

The P2-7 test suite (`tests/paper_trading/test_portfolio_reconciliation.py`) contains 38 automated tests:
- **Group 1**: Position reconciliation, long/short mismatch, direction inversion, tolerances (Tests 1–7).
- **Group 2**: Cash & balance reconciliation (Tests 8–9).
- **Group 3**: Order reconciliation & orphan broker orders (Tests 10–12).
- **Group 4**: Execution reconciliation & duplicate deduplication (Tests 14–17).
- **Group 5**: Broker API failures & stale data detection (Tests 21–26).
- **Group 6**: Safe execution import & repair (Tests 36–37).
- **Group 7**: Concurrency & multi-worker safety (Test 38).
- **Group 8**: Critical scenario suite (Tests Critical 1–8).
- **Group 9**: VWAP, fees, partial API failure, UNKNOWN resolution, halt scopes, 13-asset universe, and regressions (Tests 18, 19, 25, 28, 34, 35, 49, 50).

---

## 25. Critical Scenarios Results

| Critical Scenario | Fault Injected | Reconciliation Outcome | Safety Action | Repair Success |
|---|---|---|---|:---:|
| **Critical 1** | Broker Position Drift ($0.5 \to 0.6$) | `CRITICAL_DRIFT` | Halts BTC; no overwrite | N/A |
| **Critical 2** | Orphan Broker Order | `CRITICAL_DRIFT` | Trading halted | N/A |
| **Critical 3** | Missing Broker Execution | `CRITICAL_DRIFT` | Halts trading | Imported $\to$ `HEALTHY` |
| **Critical 4** | UNKNOWN Order Recovery | `HEALTHY` | Reconciled to FILLED | Exactly 1 fill |
| **Critical 5** | Partial Fill Drift ($0.4 \to 0.6$) | `CRITICAL_DRIFT` | Halts trading | Imported $0.2 \to$ `HEALTHY` |
| **Critical 6** | Broker API Unavailable | `DATA_UNAVAILABLE` | Global halt; zero false match | Fail-closed |
| **Critical 7** | Startup Safety Gate | `CRITICAL_DRIFT` | Prevents trading resumption | Fail-closed |
| **Critical 8** | Crash During Repair | `HEALTHY` on restart | Replays without double-fill | Deterministic |

---

## 26. Known Limitations

1. **Exchange Trade History Pruning**: If an exchange prunes trades older than 24 hours, reconciliation must rely on account balance audits.
2. **Snapshot Asynchrony**: Positions and open orders are fetched via distinct REST endpoints; rapid fills occurring between calls are handled via subsequent reconciliation cycles.

---

## 27. Production Compatibility

- **Production Oracle Cloud Database**: Untouched (`data/live_state.json`, `oms.db`).
- **Production Balances & Positions**: Unaltered.
- **Zero Live Credentials**: Tests executed with `FakeBroker` simulation harness.

---

## 28. Deferred Work

- **P2-8**: 7-Day Multi-Asset Continuous Soak Test on staging environments.
