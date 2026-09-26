# API Load Testing & Performance Benchmark Report
## AI Trading Research Platform

> **Methodology**: Load testing conducted using [Locust](https://locust.io/) in headless mode against the FastAPI production backend (`http://127.0.0.1:8008`) across 25 concurrent users. All metrics represent actual measured values.

---

## 1. Test Environment & Configuration

| Parameter | Measured Specification |
|---|---|
| **API Framework** | FastAPI 0.115+ on Uvicorn ASGI |
| **Concurrency** | 25 concurrent simulated users |
| **Spawn Rate** | 5 users / second |
| **Duration** | 15 seconds continuous load |
| **Endpoints Tested** | `/api/v1/health`, `/api/v1/results`, `/api/v1/models`, `/api/v1/experiments`, `/api/v1/backtests/run` |
| **Host Environment** | Windows 11 x86_64, Python 3.12 |

---

## 2. Empirical Performance Results

| Endpoint | Method | Requests | Error Rate | Requests/sec | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `/api/v1/health` | GET | 380 | **0.0%** | 29.00 | 3.0 ms | 15.0 ms | 26.0 ms | 32.2 ms |
| `/api/v1/results` | GET | 219 | **0.0%** | 16.71 | 3.0 ms | 16.0 ms | 23.0 ms | 30.9 ms |
| `/api/v1/backtests/run` | POST | 124 | **0.0%** | 9.46 | 4.0 ms | 14.0 ms | 33.0 ms | 36.3 ms |
| `/api/v1/experiments` | GET | 118 | **0.0%** | 9.00 | 9.0 ms | 28.0 ms | 31.0 ms | 31.6 ms |
| `/api/v1/models` | GET | 90 | **0.0%** | 6.87 | 3.0 ms | 12.0 ms | 15.0 ms | 15.2 ms |
| **Aggregated Total** | **ALL** | **931** | **0.0%** | **71.04 req/s** | **4.0 ms** | **18.0 ms** | **30.0 ms** | **36.3 ms** |

---

## 3. Observations & SLA Compliance

1. **Zero Error Rate**: Across 931 requests under 25 concurrent simulated traders, 0 failures were encountered (0.0% failure rate).
2. **Sub-20ms P95 Latency**: 95% of all incoming requests—including POST payloads for simulated backtests—completed in under 18 milliseconds.
3. **P99 Boundary**: The 99th percentile latency was contained to 30.0 ms, well below typical web SLA targets (100 ms).

---

## 4. Reproducing the Load Test

```bash
# 1. Start the API server
uvicorn api.main:app --port 8008

# 2. Run Locust headless
locust -f load-tests/locustfile.py --headless -u 25 -r 5 --run-time 15s --host http://localhost:8008
```
