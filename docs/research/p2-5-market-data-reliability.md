# P2-5 — Production-Grade Market Data Reliability, WebSocket Heartbeat, Stale Data Detection & REST Fallback

**Status:** CLOSED  
**Author:** Principal Quantitative Systems Engineer & Trading Infrastructure Reliability Engineer  
**Branch:** `feature/p2-5-market-data-reliability`  
**Repository:** `ajay1951/ai-trading-research-platform`  
**Deployment Tier:** LOCAL + STAGING VALIDATED (Oracle Cloud Production Untouched)  

---

## 1. Executive Summary

Phase **P2-5: Market Data Reliability** establishes a formally defined, deterministic, observable, and fail-closed market-data ingestion and health monitoring system. The core operational invariant enforced across the entire quantitative trading pipeline is:

$$\text{UNTRUSTED / STALE / INCOMPLETE MARKET DATA} \implies \text{TRADING NOT PERMITTED} \implies \text{ZERO NEW STRATEGY ORDERS}$$

The platform guarantees that trading decisions and portfolio rebalances are executed strictly from a complete, validated, point-in-time-consistent dataset across the canonical 13-asset quantitative ranking universe. The system distinguishes transport-layer connectivity from protocol-level heartbeats and actual market-data progression, handles WebSocket dropouts with bounded exponential backoff, recovers missing candles via validated REST fallback, deduplicates messages via a bounded LRU cache, rejects out-of-order updates, and enforces a centralized Trading Safety Gate that halts order generation whenever data integrity is compromised.

---

## 2. Existing Architecture Audit

Prior to P2-5, the platform relied on disparate market data polling and execution logic across `execution/live_momentum_daemon.py` and research scripts.

| Component | Existing Implementation | Reliability Gap | P2-5 Implementation Action |
|---|---|---|---|
| **WebSocket Transport** | Mock / CCXT polling | No heartbeat timeout or silent disconnect detection | Implemented `MarketDataFreshnessEngine` and `MarketDataWatchdog` |
| **Heartbeat / Watchdog** | Basic polling loop | Socket could stay open indefinitely without producing events | Built protocol-level watchdog tracking `last_heartbeat_ms` vs `last_valid_event_ms` |
| **Data Freshness** | Hardcoded latency checks | Conflated quote latency with 1-hour finalized bar cadences | Stream-specific cadence models with grace periods |
| **OHLCV Validation** | Research DataFrame validator | Not applied inline to incoming stream messages | Integrated `MarketDataValidator` enforcing finite positive prices and OHLC invariants |
| **Deduplication** | None in live ingestion | Duplicate ticks/candles could re-trigger indicator calculation | Created `CandleDeduplicatorAndOrderingTracker` with LRU cache |
| **Out-of-Order Handling** | Timestamp sorting in batch | Delayed older messages could overwrite newer live state | Strict monotonicity tracker rejecting older timestamps from live state |
| **Gap Detection** | Offline delta scan | No inline missing-candle detection or backfill verification | Implemented `CandleGapDetector` with automated backfill validation |
| **13-Asset Sync** | Individual symbol loops | Could proceed with partial (e.g. 12-asset) universe | Implemented `CrossSectionalUniverseValidator` requiring exact point-in-time alignment |
| **REST Fallback** | Uncoordinated fallback | Race conditions where older REST response overwrote newer WS data | Implemented `MarketDataRecoveryCoordinator` with deterministic conflict resolution |
| **Trading Safety Gate** | Ad-hoc try/except skips | No centralized fail-closed check before order creation | Created canonical `TradingSafetyGate` blocking order paths upon data failure |

---

## 3. Market-Data Sources

The system supports dual ingestion channels for Binance public spot and futures data:
1. **WebSocket Streams:**
   - Real-time Kline/candlestick streams (`<symbol>@kline_1h`)
   - Ticker streams (`<symbol>@ticker`)
   - Protocol ping/pong heartbeats
2. **REST Fallback Endpoints:**
   - Binance Public Market Data API (`/api/v3/klines`, `/fapi/v1/klines`)
   - Historical multi-bar pagination and gap backfill

---

## 4. Connection Health Model

The canonical `MarketDataStatus` enum establishes unambiguous authoritative health states:

```python
class MarketDataStatus(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    RECOVERING = "RECOVERING"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"
```

### Critical Distinction
- $\text{WebSocket Connected} \neq \text{Data Healthy}$ (A socket may be open while silent or emitting duplicate/stale candles).
- $\text{REST Request Succeeded} \neq \text{Data Fresh}$ (A REST response may return old cached bars or incomplete candles).

---

## 5. Heartbeat & Connection Watchdog Design

The watchdog independently monitors three distinct signals:
1. `last_transport_activity_ms`: Raw byte transmission on socket.
2. `last_heartbeat_ms`: Protocol ping/pong acknowledgment.
3. `last_valid_market_event_ms`: Authoritative validated market data update.

### Watchdog Timeout Behavior
If no heartbeat or market event is received within `WS_HEARTBEAT_TIMEOUT_SECONDS` (default: 30.0s), the watchdog immediately marks the stream `UNAVAILABLE`, blocks strategy orders, and initiates bounded reconnection.

---

## 6. Freshness Thresholds

Stream freshness is evaluated based on specific stream cadence:
- **Quote / Ticker Streams:** Maximum allowable age = 10.0s.
- **Finalized 1-Hour Candles:** Expected candle close is at `timestamp_ms + 3600000`. Maximum allowable delay after expected close = 300.0s (5-minute grace period).

---

## 7. Timestamp Integrity & Clock Skew

The `MarketDataValidator` validates:
- Non-negative, positive epoch millisecond timestamps ($t > 0$, $t \ge 1577836800000$).
- Forward clock drift bounded by $\text{MAX\_CLOCK\_SKEW\_SECONDS} = 5.0\text{s}$.
- Timestamps into the distant future ($t > \text{now} + 5\text{s}$) are rejected with `FUTURE_TIMESTAMP_CLOCK_SKEW`.
- Seconds vs milliseconds automatic normalization.
- Injected monotonic elapsed time for watchdog deadlines vs UTC-aware timestamps for event validation.

---

## 8. Message Validation

Before any message enters internal state, it is validated for structural and numeric integrity:
- Rejects `NaN`, `Inf`, `-Inf`, `None` in mandatory fields.
- Price must be strictly positive ($P > 0$).
- Volume must be strictly non-negative ($V \ge 0$).
- Rejects malformed JSON, truncated CCXT arrays, and unsupported stream schemas.

---

## 9. OHLCV Invariants

Every candle must satisfy:
$$\text{High} \ge \text{Low}$$
$$\text{High} \ge \text{Open} \quad \text{and} \quad \text{High} \ge \text{Close}$$
$$\text{Low} \le \text{Open} \quad \text{and} \quad \text{Low} \le \text{Close}$$

Any violation immediately rejects the candle and marks the stream `INVALID`.

---

## 10. Finalized Candle Handling

The LightGBM cross-sectional ranking strategy requires finalized bars (e.g. `ohlcv[-2]` or `is_final=True`).
- In-progress candles (`is_final=False`) are flagged as `INCOMPLETE_EXCLUDED` and cannot enter the ranking feature pipeline.
- Only finalized bars update the authoritative decision state.

---

## 11. Duplicate Message Handling

Deduplication uses the canonical deterministic tuple:
$$\text{Identity} = (\text{exchange}, \text{symbol}, \text{timeframe}, \text{timestamp\_ms}, \text{is\_final})$$

Incoming duplicates are recorded in a bounded LRU cache (5,000 items) and ignored (`DUPLICATE_IGNORED`), preventing indicator re-computation and duplicate signal generation.

---

## 12. Out-of-Order Message Handling

The `CandleDeduplicatorAndOrderingTracker` tracks the latest processed timestamp per symbol.
- If $t_{\text{incoming}} < t_{\text{latest}}$, the incoming record is flagged `OUT_OF_ORDER_IGNORED` and rejected from modifying the live state.
- Ensures delayed REST responses or replayed socket messages never overwrite newer authoritative market data.

---

## 13. Candle Continuity & Gap Detection

The `CandleGapDetector` validates sequential continuity:
$$t_k - t_{k-1} == \Delta t \quad (\text{e.g. } 3,600,000\text{ ms for 1h})$$
If a gap is detected ($t_k > t_{k-1} + \Delta t$), the affected asset is marked `INCOMPLETE`, trading is blocked, and backfill is requested.

---

## 14. Backfill Validation Policy

When missing candles are fetched via REST:
1. The backfilled sequence is verified for interval continuity ($t_{k} = t_{k-1} + \Delta t$).
2. Merged dataset is checked for zero remaining gaps.
3. Stream health transitions to `HEALTHY` only when continuity across the entire required historical window is confirmed.

---

## 15. 13-Asset Cross-Sectional Synchronization

The quantitative strategy selects Top-2 assets from the canonical 13-asset universe:
`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `DOGEUSDT`, `ADAUSDT`, `AVAXUSDT`, `LINKUSDT`, `NEARUSDT`, `LTCUSDT`, `DOTUSDT`, `SUIUSDT`.

### Universe Invariants
1. **Full Universe Requirement:** All 13 assets must be individually `HEALTHY`. If even 1 asset is stale or missing, the universe status becomes `INCOMPLETE` / `STALE`, blocking ranking. No silent universe shrinkage to 12.
2. **Aligned Decision Cutoff:** All 13 assets must share the identical finalized cutoff timestamp. Misaligned cutoffs reject the dataset.

---

## 16. WebSocket Reconnection

Reconnection implements bounded exponential backoff:
$$\text{Delay}(k) = \min(\text{InitialDelay} \times 2^{k-1}, \text{MaxDelay}) \quad (\text{Initial: } 0.5\text{s, Max: } 8.0\text{s})$$

**Reconnection Invariant:** Reconnecting the socket transitions the state to `RECOVERING`, **never** directly to `HEALTHY`. Trading permission is restored only after the 13-asset universe is validated.

---

## 17. REST Fallback

When WebSocket streams fail or drop out:
1. REST fallback is dispatched per symbol.
2. Handles HTTP 429 rate limits, request timeouts, and server errors gracefully.
3. Validates that REST responses are fresh, finalized, and structurally valid before acceptance.

---

## 18. Fallback Race Conditions

When WebSocket reconnects while a REST fetch is in flight:
- Deduplication keys guarantee identical bars are accepted exactly once.
- Monotonic ordering checks guarantee older REST responses ($T-1$) cannot overwrite newer WebSocket data ($T$).

---

## 19. Canonical Trading Safety Gate

The `TradingSafetyGate` acts as the single point-of-control between market data ingestion and order submission:

```
                  MARKET DATA INGESTION
                            |
                            v
             DATA VALIDATION & FRESHNESS ENGINE
                            |
                            v
            13-ASSET CROSS-SECTIONAL SYNC
                            |
                            v
                   TRADING SAFETY GATE
                            |
              +-------------+-------------+
              |                           |
           HEALTHY                    UNHEALTHY
              |                           |
              v                           v
      SIGNAL GENERATION           ZERO NEW ORDERS
              |                  (POSITIONS PRESERVED)
              v
          RISK CHECK
              |
              v
           OMS / P2-1 STATE MACHINE
```

---

## 20. Missed Rebalance Policy

The strategy rebalances every 48 hours.
- If data is unhealthy at the scheduled rebalance cutoff, the rebalance is recorded as `SKIPPED_UNTRUSTED_DATA`.
- Stale order intents are **never** executed post-recovery.
- Evaluation resumes cleanly at the next eligible scheduled decision cutoff.

---

## 21. Observability

### Prometheus Metrics
- `market_data_connected`: Gauge (1/0)
- `market_data_last_valid_event_timestamp`: Gauge (ms)
- `market_data_age_seconds`: Gauge (s)
- `market_data_messages_total`: Counter
- `market_data_invalid_messages_total`: Counter
- `market_data_duplicate_messages_total`: Counter
- `market_data_out_of_order_total`: Counter
- `market_data_gap_events_total`: Counter
- `market_data_stale_events_total`: Counter
- `market_data_disconnects_total`: Counter
- `market_data_reconnects_total`: Counter
- `market_data_rest_fallback_total`: Counter
- `market_data_rest_fallback_failures_total`: Counter
- `market_data_trading_blocks_total`: Counter
- `market_data_recovery_duration_seconds`: Histogram

### Structured Log Events
- `MARKET_DATA_CONNECTED`, `MARKET_DATA_DISCONNECTED`, `MARKET_DATA_HEARTBEAT_TIMEOUT`, `MARKET_DATA_STALE`, `MARKET_DATA_INVALID`, `MARKET_DATA_DUPLICATE`, `MARKET_DATA_OUT_OF_ORDER`, `MARKET_DATA_GAP_DETECTED`, `MARKET_DATA_BACKFILL_STARTED`, `MARKET_DATA_BACKFILL_COMPLETE`, `MARKET_DATA_REST_FALLBACK_STARTED`, `MARKET_DATA_REST_FALLBACK_FAILED`, `MARKET_DATA_RECOVERY_COMPLETE`, `STRATEGY_ORDER_BLOCKED_DATA_UNHEALTHY`.

---

## 22. Fault-Injection Architecture

`MockMarketDataFeed` provides deterministic offline fault injection:
- `DISCONNECT`, `HEARTBEAT_TIMEOUT`, `STALE_MESSAGE`, `DUPLICATE_MESSAGE`, `OUT_OF_ORDER`, `MALFORMED_MESSAGE`, `MISSING_CANDLE`, `INVALID_OHLC`, `FUTURE_TIMESTAMP`, `REST_TIMEOUT`, `REST_STALE`, `RATE_LIMIT_429`.

---

## 23. Test Matrix Summary

The automated test suite in `tests/paper_trading/test_market_data_reliability.py` executes 74 tests covering:
- **Group A (Tests 1–8):** WebSocket connections, heartbeats, timeouts, silent dropouts, reconnect backoff.
- **Group B (Tests 9–16):** Freshness thresholds, timestamp integrity, clock skew, second/millisecond normalization.
- **Group C (Tests 17–26):** Valid OHLC, negative/zero prices, NaN/Inf rejection, volume anomalies, malformed JSON.
- **Group D (Tests 27–34):** Incomplete vs finalized bars, deduplication, out-of-order rejection, gap backfill.
- **Group E (Tests 35–42):** 13-asset universe completeness, cutoff timestamp alignment, zero partial shrinkage.
- **Group F (Tests 43–50):** REST fallback success, timeouts, stale/malformed responses, 429 rate limits, race conditions.
- **Group G (Tests 51–60):** Trading Safety Gate enforcement, zero new orders, position preservation, missed rebalance policy.
- **Group H & Scenarios (Tests 61–74):** Determinism, immutability, metric logging, and End-to-End Safety Scenarios 1 through 8.

---

## 24. Performance & Resource Safety

- **LRU Deduplication Cache:** Fixed size (5,000 entries) preventing unbounded memory consumption.
- **Evaluation Latency:** Sub-millisecond single-asset validation (<0.02ms per candle).
- **Universe Sync Latency:** Complete 13-asset health evaluation executed in <0.25ms.
- **Zero Event Loop Blocking:** Synchronous calculations are lightweight and memory-efficient.

---

## 25. Production Compatibility

- Oracle Cloud deployment files (`data/live_state.json`, `oms.db`) remained 100% isolated and unmodified.
- Staging and test databases utilized temporary, isolated SQLite storage.
- All 175 baseline tests and 74 new P2-5 tests pass without warnings or regressions.

---

## 26. Deployment & Rollback

- **Deployment Status:** LOCAL + STAGING VALIDATED.
- **Rollback Safety:** Standalone module `data/market_data_health.py` is fully decoupled and does not alter database schemas or strategy state. Rollback requires simple checkout of the parent branch.

---

## 27. Known Limitations

1. High-frequency tick-level microsecond order book validation is outside the scope of the 1-hour bar execution strategy.
2. Cross-exchange multi-venue arbitrage synchronization is deferred to future multi-broker phases.

---

## 28. Deferred P2 Work

- **P2-6:** Broker/API Fault Injection (Network jitter, exchange error codes, synthetic order dropouts).
- **P2-7:** Portfolio Reconciliation (Internal ledger vs exchange wallet balance continuous audit).
- **P2-8:** Seven-Day Continuous Soak (Multi-day operational endurance test).
