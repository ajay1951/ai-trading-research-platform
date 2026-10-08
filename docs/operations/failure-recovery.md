# Operations Failure & Recovery Protocol

**Audit Date:** October 2026  
**Auditor Profile:** Production Backend & Reliability Engineer  
**Scope:** Autonomous live daemon, OMS persistence, circuit breakers, and edge-case handling.

---

## 1. Failure Modes & Automated Recovery Matrix

| Failure Mode | Detection Mechanism | Automated System Response | Recovery Behavior | Safe State Guarantee |
|---|---|---|---|:---:|
| **Exchange API Unavailable (503/504)** | CCXT `NetworkError` / HTTP status catch | Exponential backoff (1s, 2s, 4s, 8s up to 60s max) | Resumes polling on next 1h boundary after connection restored | Yes (No orders emitted) |
| **Network Timeout** | Socket read timeout (>10.0s) | Increments error counter in `CircuitBreaker` | Retries current candle fetch; trips breaker if $>5$ consecutive errors | Yes (Zero fill simulation) |
| **Malformed Market Data** | `OHLCVValidator` schema check | Rejects malformed payload; logs error | Skips calculation cycle; relies on previous state | Yes (No state corruption) |
| **Duplicate Candle Timestamp** | `test_duplicate_candles.py` / `validator.py` | Drops duplicate row; keeps first valid candle | Dedupes bar buffer before feature extraction | Yes (No double-execution) |
| **Missing Candle / Gap in Feed** | Time delta delta check ($\Delta t > 1\text{h}$) | Flags gap; triggers backfill routine via REST | Synchronizes missing bars before evaluating signal | Yes (Prevents false jumps) |
| **Process Kill / Server Crash** | Host process termination | State saved to `data/live_state.json` on each loop | On startup, daemon reloads open positions, cash balance, and entry prices | Yes (Zero position loss) |
| **Corrupted State File (`.json`)** | JSON decoding error on startup | Logs critical error; attempts load from `.backup` or `oms.db` | Falls back to SQLite OMS transaction logs | Yes (Halts if unreconcilable) |
| **SQLite DB Lock / Unavailable** | `sqlite3.OperationalError` (Busy/Locked) | Thread-local connections with timeout retry (5.0s) | Retries query; logs alert to Prometheus | Yes (ACID transaction safety) |
| **Invalid Model Output (NaN / Inf)**| Assertion check on probabilities ($0 \le P \le 1$) | Neutralizes signal to 0.0 (Cash defense) | Bypasses trade execution; triggers warning log | Yes (Defaults to 100% Cash) |
| **Excessive Execution Slippage** | Realized fill price vs arrival price | `CircuitBreaker.check_slippage()` detects drift $>1.5\%$ | Immediately trips circuit breaker; halts new orders | Yes (Emergency trade freeze) |
| **Consecutive API Rejections** | Order rejection counter ($\ge 5$) | `CircuitBreaker.record_error()` triggers lock | Locks execution engine; requires manual operator reset | Yes (Prevents runaway API thrashing) |

---

## 2. Operational Health & Verification Endpoints

1. **Liveness & Readiness Check:**
   `GET /api/v1/health` -> Returns `{"status": "healthy", "service": "AI Trading Research Platform API", "timestamp": "...", "database": "connected"}`.
2. **Prometheus Telemetry:**
   `GET /metrics` -> Exposes operational counters (`api_requests_total`, `api_request_duration_seconds`).
3. **Emergency Circuit Breaker Status:**
   Observable in `execution/live_momentum_daemon.py` via `self.circuit_breaker.is_tripped`.
