# AI Trading Research Platform — Final Engineering Roadmap

## Objective

Finish the AI Trading Research Platform as a credible, reproducible, technically polished portfolio project.

**Primary goal:** improve proof, reproducibility, security, testing, observability, and presentation.

**Do not add new major AI features unless they directly produce evidence for an existing capability.**

---

# Execution Order

## Phase 1 — Get CI Fully Green

### Tasks
- [ ] Check the latest GitHub Actions run.
- [ ] Fix dependency installation failures.
- [ ] Fix linting/Flake8 failures.
- [ ] Run the complete pytest suite.
- [ ] Fix all failing tests.
- [ ] Verify API, backtest, leakage, risk, and execution tests.
- [ ] Verify Docker build if included in CI.
- [ ] Re-run CI after fixes.

### Acceptance Criteria

```text
Lint        PASS
Unit tests  PASS
Integration PASS
Docker      PASS
CI          GREEN
```

Do not claim CI is passing until GitHub actually reports a successful run.

---

## Phase 2 — Make the Test Suite Reproducible

### Tasks
- [ ] Verify Python version.
- [ ] Verify requirements are complete.
- [ ] Verify a clean virtual environment works.
- [ ] Run the complete test suite from a clean environment.
- [ ] Document the exact test command.

### Command

```bash
pytest -q
```

Document the actual test count produced by the current repository. Do not hard-code an old count if it changes.

---

## Phase 3 — Reproduce the Trading Benchmark

### Tasks
- [ ] Run `training.benchmark_suite`.
- [ ] Verify dataset and version.
- [ ] Record dataset hash.
- [ ] Record start/end dates.
- [ ] Record asset.
- [ ] Record train/validation/test split.
- [ ] Record embargo.
- [ ] Record transaction fees.
- [ ] Record slippage.
- [ ] Record model configuration.
- [ ] Record random seed where applicable.
- [ ] Generate machine-readable results.

### Command

```bash
python -m training.benchmark_suite
```

### Recommended Artifacts

```text
artifacts/
└── benchmark/
    ├── benchmark_results.csv
    ├── benchmark_results.json
    └── run_metadata.json
```

### Metadata

```json
{
  "dataset": "BTCUSDT-1h",
  "dataset_version": "v1",
  "dataset_hash": "...",
  "period_start": "...",
  "period_end": "...",
  "train_ratio": 0.70,
  "validation_ratio": 0.15,
  "test_ratio": 0.15,
  "embargo_bars": 24,
  "transaction_fee": 0.0004,
  "slippage": 0.0002
}
```

Replace all placeholders with actual values before committing.

---

## Phase 4 — Verify Every README Result

### Tasks
- [ ] Re-run benchmark.
- [ ] Compare generated results with README.
- [ ] Verify returns.
- [ ] Verify Sharpe.
- [ ] Verify maximum drawdown.
- [ ] Verify trade count.
- [ ] Verify benchmark period.
- [ ] Verify transaction costs.
- [ ] Verify execution assumptions.
- [ ] Remove unsupported numbers.
- [ ] Never manually alter results to match README.

### Benchmark Table

Use actual measured values:

| Model | Return | Sharpe | Max Drawdown | Trades |
|---|---:|---:|---:|---:|
| Buy & Hold | Actual | Actual | Actual | Actual |
| MA | Actual | Actual | Actual | Actual |
| Logistic Regression | Actual | Actual | Actual | Actual |
| Random Forest | Actual | Actual | Actual | Actual |
| LightGBM | Actual | Actual | Actual | Actual |
| LSTM | Actual | Actual | Actual | Actual |
| Transformer | Actual | Actual | Actual | Actual |

A weak model result is acceptable. An unreproducible result is not.

---

## Phase 5 — Verify Failure Analysis

### Goal

Turn `docs/FAILURE_ANALYSIS.md` into traceable research evidence.

### For every major experiment
- [ ] Assign experiment ID.
- [ ] Record Git commit SHA.
- [ ] Record dataset version/hash.
- [ ] Record model.
- [ ] Record configuration.
- [ ] Record validation methodology.
- [ ] Record output artifact.
- [ ] Record conclusion.

### Example

```text
Experiment: EXP-007
Commit: <commit SHA>
Dataset: BTCUSDT-1h-v1
Model: Transformer
Split: 70/15/15
Embargo: 24 bars
Output: artifacts/experiments/EXP-007/
```

### Verify existing claims
- [ ] High-churn strategy failure after transaction costs.
- [ ] Transformer overfitting.
- [ ] Rejected/pruned features.
- [ ] Changes to execution assumptions.
- [ ] Out-of-sample performance.
- [ ] Transaction-cost impact.

Every numerical claim must be traceable to an actual experiment.

---

## Phase 6 — Fix API Security

### Current Issue to Review

```python
allow_origins=["*"]
allow_credentials=True
```

### Tasks
- [ ] Replace wildcard CORS with explicit origins.
- [ ] Move allowed origins to environment configuration.
- [ ] Review authentication.
- [ ] Review authorization.
- [ ] Review API key handling.
- [ ] Verify `.env` is ignored.
- [ ] Search repository for secrets.
- [ ] Review request validation.
- [ ] Review exception handling.
- [ ] Review rate limiting.
- [ ] Review API documentation exposure.
- [ ] Review database access.
- [ ] Review logging for secrets.

### Recommended Pattern

```python
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000"
).split(",")
```

Then:

```python
allow_origins=ALLOWED_ORIGINS
```

### Acceptance Criteria

- No wildcard production CORS configuration.
- No committed credentials.
- No obvious secret leakage.

---

## Phase 7 — Repository Hygiene

### Review

```text
.kombai/
build_log.txt
tests/legacy/
```

### Tasks
- [ ] Remove unnecessary generated files.
- [ ] Remove temporary development logs.
- [ ] Remove unused legacy code.
- [ ] Review `.gitignore`.
- [ ] Review `.dockerignore`.
- [ ] Check for `.env` files.
- [ ] Check for credentials.
- [ ] Check for virtual environments.
- [ ] Check for large generated files.
- [ ] Check for IDE artifacts.

### Commands

```bash
git status
git ls-files
```

---

## Phase 8 — Run Load Tests

### Existing Resource

```text
load-tests/locustfile.py
```

### Tasks
- [ ] Run Locust.
- [ ] Test realistic concurrency.
- [ ] Measure requests/second.
- [ ] Measure P50 latency.
- [ ] Measure P95 latency.
- [ ] Measure P99 latency.
- [ ] Measure error rate.
- [ ] Record concurrent users.
- [ ] Save test configuration.
- [ ] Document test environment.

### Metrics

```text
Requests/sec
P50
P95
P99
Error rate
Concurrent users
```

Only publish numbers generated by actual tests.

---

## Phase 9 — Verify Observability

### Tasks
- [ ] Verify Prometheus configuration.
- [ ] Expose application metrics.
- [ ] Add request count metrics.
- [ ] Add request latency metrics.
- [ ] Add backtest duration metrics.
- [ ] Add experiment metrics.
- [ ] Add model inference latency.
- [ ] Add ingestion failure metrics.
- [ ] Verify metrics are collected.
- [ ] Create Grafana dashboards if Grafana is part of deployment.
- [ ] Capture useful screenshots/evidence.

### Recommended Metrics

```text
api_requests_total
api_request_duration_seconds
backtest_duration_seconds
experiment_runs_total
model_inference_latency
data_ingestion_failures
```

---

## Phase 10 — Architecture Documentation

### Tasks
- [ ] Create/update architecture diagram.
- [ ] Explain data flow.
- [ ] Explain model flow.
- [ ] Explain validation flow.
- [ ] Explain risk flow.
- [ ] Explain API architecture.
- [ ] Explain storage.
- [ ] Explain background workers.
- [ ] Explain observability.

### Architecture

```text
Market Data
    ↓
Data Validation
    ↓
Feature Engineering
    ↓
┌──────────────────────┐
│ Baseline Models      │
│ ML Models            │
└──────────┬───────────┘
           ↓
Research Engine
           ↓
Walk-Forward Validation
           ↓
Out-of-Sample Evaluation
           ↓
Risk Engine
           ↓
Research Results
```

---

## Phase 11 — Reproducibility Documentation

### README Should Include

```markdown
## Reproducibility

### Environment

Python 3.10+

### Install

pip install -r requirements.txt

### Tests

pytest -q

### Benchmark

python -m training.benchmark_suite

### API

uvicorn api.main:app --reload

### Load Testing

locust -f load-tests/locustfile.py
```

Also document:

- Dataset version.
- Dataset hash.
- Time period.
- Asset universe.
- Temporal split.
- Embargo.
- Transaction costs.
- Slippage.
- Random seeds.
- Model configurations.

---

## Phase 12 — Final README Rewrite

### Recommended Opening

```markdown
# AI Trading Research Platform

A quantitative research platform for evaluating machine-learning
trading strategies under temporal validation, transaction costs,
execution constraints, risk controls, and anti-leakage testing.
```

### Show Evidence Near the Top

```text
Automated Tests
Temporal Validation
Anti-Leakage Tests
Walk-Forward Evaluation
Transaction-Cost Modeling
Risk Engine
FastAPI Research API
Docker
CI/CD
Load Testing
Prometheus
Failure Analysis
```

### Avoid Unsupported Claims

Avoid phrases such as:

```text
Institutional-grade
Hedge-fund-grade
HFT-grade
Production-ready
100% reliable
Guaranteed performance
```

unless the repository contains strong evidence supporting the exact claim.

---

## Phase 13 — Final GitHub Audit

### Code
- [ ] No obvious dead code.
- [ ] No secrets.
- [ ] No unexplained generated files.
- [ ] No broken imports.
- [ ] No unexplained critical TODOs.
- [ ] Consistent naming.
- [ ] Reasonable project structure.

### Tests
- [ ] Full test suite passes.
- [ ] Leakage tests pass.
- [ ] API tests pass.
- [ ] Backtest tests pass.
- [ ] Risk tests pass.
- [ ] Execution tests pass.

### Research
- [ ] Results reproducible.
- [ ] Dataset documented.
- [ ] Validation documented.
- [ ] Costs documented.
- [ ] Failure analysis traceable.
- [ ] README numbers match artifacts.

### Infrastructure
- [ ] CI green.
- [ ] Docker build works.
- [ ] Load test completed.
- [ ] Observability verified.
- [ ] Security configuration reviewed.

### Documentation
- [ ] README polished.
- [ ] Architecture documented.
- [ ] Reproducibility documented.
- [ ] Benchmark results documented.
- [ ] Screenshots added where useful.

---

# Final Completion Gate

The project is finished when all of these are true:

```text
[ ] CI is GREEN
[ ] Full test suite passes
[ ] Benchmark is reproducible
[ ] Dataset/version/hash documented
[ ] README numbers match generated results
[ ] Failure analysis is traceable
[ ] API security reviewed
[ ] Repository cleaned
[ ] Load testing completed
[ ] Observability verified
[ ] Architecture documented
[ ] Reproducibility documented
[ ] README rewritten around evidence
[ ] Final GitHub audit completed
```

---

# What NOT To Do

Do not spend the next iteration adding:

- Another LLM.
- Another trading agent.
- Another prediction model.
- Another dashboard.
- Another strategy.
- Another AI feature.
- Large amounts of generated code without a measurable purpose.

The project is already feature-rich enough.

The remaining work is primarily:

```text
PROOF
  +
REPRODUCIBILITY
  +
SECURITY
  +
TESTING
  +
OBSERVABILITY
  +
DOCUMENTATION
```

---

# Final Target

### Before

> I built an AI trading system with many models and features.

### After

> I built a reproducible quantitative research platform with temporal validation, anti-leakage testing, transaction-cost modeling, risk controls, automated testing, CI/CD, performance testing, observability, and documented failure analysis.

---

# Suggested Final Repository Structure

```text
ai-trading-research-platform/
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── api/
├── agents/
├── backtesting/
├── data/
├── docs/
│   ├── adr/
│   └── FAILURE_ANALYSIS.md
│
├── execution/
├── observability/
├── risk/
├── tests/
│   ├── api/
│   ├── backtest/
│   ├── data/
│   ├── execution/
│   ├── leakage/
│   └── risk/
│
├── training/
├── load-tests/
│   └── locustfile.py
│
├── artifacts/
│   └── benchmark/
│
├── Dockerfile
├── .dockerignore
├── .env.example
├── .gitignore
├── README.md
├── RESEARCH.md
├── RESULTS.md
└── SYSTEM_DOCUMENTATION.md
```

---

# Execution Rule

**Complete the phases in order.**

Do not polish the README before the benchmark and CI are verified.

Do not publish performance numbers before reproducing them.

Do not call the system production-ready before reviewing security.

Do not add major features while core evidence is still missing.

**Finish the proof before expanding the product.**
