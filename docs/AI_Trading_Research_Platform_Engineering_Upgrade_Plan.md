# AI Trading Research Platform
## Engineering Upgrade Plan

> Objective: Upgrade the repository so a technical recruiter can verify evidence of ML Systems Engineering, Backend Engineering, Quantitative Experimentation, Reliable Software Engineering, and Reproducible Research.

## 1. Target Outcome

The repository should demonstrate the complete lifecycle:

```text
Market Data
    ↓
Data Validation
    ↓
Feature Engineering
    ↓
Temporal Dataset Construction
    ↓
Baseline Models
    ↓
ML Training
    ↓
Experiment Tracking
    ↓
Model Evaluation
    ↓
Walk-Forward Validation
    ↓
Backtesting
    ↓
Transaction Costs + Slippage
    ↓
Risk Engine
    ↓
Statistical Evaluation
    ↓
Research Report
    ↓
Paper Trading / Controlled Deployment
```

## 2. Priority Levels

| Priority | Meaning |
|---|---|
| P0 | Must fix before presenting repository |
| P1 | Required for strong technical credibility |
| P2 | Major improvement |
| P3 | Polish / differentiation |

# P0 - Repository Quality

## CI/CD

- [ ] Fix all Flake8 errors
- [ ] Run PyTest after lint succeeds
- [ ] Ensure CI executes lint and tests
- [ ] Add build validation
- [ ] Verify GitHub Actions is green

Target:

```text
Pull Request
     ↓
Lint
     ↓
Unit Tests
     ↓
Integration Tests
     ↓
ML/Data Tests
     ↓
Build
     ↓
PASS
```

## README Cleanup

- [ ] Remove all `file:///c:/Users/` links
- [ ] Replace with GitHub-relative links
- [ ] Verify every README link works
- [ ] Remove references to local development directories

## Repository Cleanup

Remove:

```text
then/
.venv/
venv/
__pycache__/
*.pyc
temporary files
local configuration
credentials
debug artifacts
```

Review and clean:

```text
scratch/
```

Recommended `.gitignore`:

```gitignore
.venv/
venv/
env/
then/
__pycache__/
*.pyc
.env
.env.*
*.log
.DS_Store
```

# P1 - Reproducible ML Experiments

## Experiment Manifests

Create:

```text
data/manifests/
```

Example:

```yaml
experiment_id: exp_001

dataset:
  name: crypto_market_data
  version: 2026-09-01
  hash: "<DATASET_HASH>"

assets:
  - BTC
  - ETH
  - SOL

timeframe: 4h

split:
  train: 0.70
  validation: 0.15
  test: 0.15
  embargo_bars: 24

model:
  name: lightgbm
  seed: 42

costs:
  fee: 0.0004
  slippage: 0.0002
```

## Dataset Versioning

For every benchmark record:

- [ ] Asset
- [ ] Exchange/source
- [ ] Timeframe
- [ ] Start date
- [ ] End date
- [ ] Number of candles
- [ ] Dataset version
- [ ] Dataset hash
- [ ] Missing candle policy
- [ ] Duplicate handling
- [ ] Timezone
- [ ] Data cleaning procedure

## Data Validation

Create:

```text
tests/data/
```

Required:

```text
test_missing_candles.py
test_duplicate_candles.py
test_out_of_order_timestamps.py
test_timestamp_alignment.py
test_timezone_consistency.py
test_invalid_prices.py
test_invalid_volume.py
```

The system must reject malformed market data before training.

# P1 - Anti-Leakage Framework

Create:

```text
tests/leakage/
```

Required:

```text
test_no_lookahead.py
test_feature_leakage.py
test_label_leakage.py
test_future_candle_mutation.py
test_scaler_fit_only_train.py
test_feature_timestamp_alignment.py
test_train_test_overlap.py
test_embargo_gap.py
```

## Future Candle Mutation

Expected behavior:

```text
Future candle changes
        ↓
Historical features must NOT change
```

## Train-Only Scaler

Correct:

```text
Scaler.fit(train)
Scaler.transform(train)
Scaler.transform(validation)
Scaler.transform(test)
```

Never:

```text
Scaler.fit(all_data)
```

- [ ] Add regression test preventing full-dataset fitting

# P1 - Temporal Validation

Document:

```text
Train:      70%
Validation: 15%
Embargo:    24 bars
Test:       15%
```

Explain:

- [ ] Why temporal splitting is required
- [ ] Why random splitting is inappropriate
- [ ] Why embargo exists
- [ ] How overlap is prevented

# P1 - Backtesting Integrity

Document:

```text
Candle t
   ↓
Features available at t
   ↓
Prediction
   ↓
Trading Signal
   ↓
Execution at t+1
   ↓
Fee
   ↓
Slippage
   ↓
Position Update
   ↓
P&L
```

Document:

- [ ] Prediction timestamp
- [ ] Execution timestamp
- [ ] Holding period
- [ ] Fees
- [ ] Slippage
- [ ] Position sizing
- [ ] Portfolio accounting
- [ ] Cash handling
- [ ] Leverage
- [ ] Order assumptions

# P1 - Transaction Cost Tests

Required:

```text
tests/backtest/test_transaction_costs.py
```

Test:

- [ ] Entry fees
- [ ] Exit fees
- [ ] Slippage
- [ ] Multiple trades
- [ ] Position changes
- [ ] Round-trip cost
- [ ] Zero-cost comparison
- [ ] Cost scaling with trade size

Verify that gross P&L exceeds net P&L when costs are applied.

# P1 - Benchmark Reproducibility

Every reported result must record:

```text
Model
Dataset
Asset Universe
Timeframe
Train Period
Validation Period
Test Period
Seed
Features
Transaction Fees
Slippage
Execution Timing
Number of Trades
```

## Benchmark Suite

Maintain:

```text
Buy & Hold
Random
Moving Average
Logistic Regression
Random Forest
LightGBM
LSTM
Transformer
```

Compare:

- [ ] Return
- [ ] Sharpe
- [ ] Sortino
- [ ] Maximum Drawdown
- [ ] Calmar
- [ ] Win Rate
- [ ] Profit Factor
- [ ] Number of Trades
- [ ] Turnover

## Standardized Results

Create:

```text
results/
├── experiments/
├── benchmark_results.csv
└── metrics.json
```

Example:

```json
{
  "experiment_id": "exp_001",
  "model": "lightgbm",
  "dataset": "crypto_2026_09",
  "seed": 42,
  "metrics": {}
}
```

# P2 - Quantitative Experimentation

## Ablation Studies

Example:

| Experiment | Features | Model | Costs |
|---|---|---|---|
| Baseline | Technical | RF | Yes |
| A | Technical + Volume | RF | Yes |
| B | Technical + Sentiment | RF | Yes |
| C | Technical + Volume | LSTM | Yes |
| D | All | Transformer | Yes |

Answer:

- Which features matter?
- Which model benefits?
- Does complexity improve out-of-sample performance?
- Does performance survive transaction costs?

## Statistical Robustness

Implement:

```text
evaluation/
├── statistical_tests.py
├── bootstrap.py
├── monte_carlo.py
└── significance.py
```

Evaluate:

- [ ] Bootstrap confidence intervals
- [ ] Monte Carlo analysis
- [ ] Statistical significance
- [ ] Parameter sensitivity
- [ ] Performance stability
- [ ] Out-of-sample robustness

Never invent or hard-code results.

## Failure Analysis

Create:

```text
docs/FAILURE_ANALYSIS.md
```

Document:

- [ ] Model underperformance
- [ ] Strategy failures
- [ ] Transaction-cost failures
- [ ] Removed features
- [ ] Rejected models
- [ ] Backtesting assumption changes

# P2 - Backend Engineering

Required:

- [ ] FastAPI
- [ ] PostgreSQL
- [ ] Redis
- [ ] Celery/background workers
- [ ] Async operations where appropriate
- [ ] Structured errors
- [ ] Request validation
- [ ] Configuration management
- [ ] Database migrations
- [ ] Health endpoints
- [ ] Logging
- [ ] API documentation

Architecture:

```text
Next.js
   ↓
FastAPI
   ↓
Service Layer
   ↓
Repository Layer
   ↓
PostgreSQL

FastAPI
   ↓
Redis
   ↓
Celery Workers
   ↓
ML / Research Jobs
```

## API

Implement as appropriate:

```text
/api/v1/health
/api/v1/experiments
/api/v1/models
/api/v1/backtests
/api/v1/results
/api/v1/research
```

Each endpoint should have:

- [ ] Input validation
- [ ] Response schema
- [ ] Error handling
- [ ] Logging
- [ ] Request ID
- [ ] Correct HTTP status codes

# P2 - Observability

Track:

```text
API latency
Inference latency
Training duration
Worker failures
Queue depth
Data ingestion failures
Model failures
Backtest duration
```

Recommended:

```text
Prometheus
    ↓
Grafana
```

Also add structured logs.

# P2 - Load Testing

Create:

```text
load-tests/
```

Possible tools:

```text
Locust
k6
```

Measure:

```text
Requests/sec
P50 latency
P95 latency
P99 latency
Error rate
Concurrent users
```

Document the test environment and configuration.

Never claim scalability without measurements.

# P2 - ML Model Lifecycle

Document:

```text
Dataset
   ↓
Training
   ↓
Experiment
   ↓
Evaluation
   ↓
Model Artifact
   ↓
Model Registry
   ↓
Inference
```

Implement where appropriate:

- [ ] Model versioning
- [ ] Model metadata
- [ ] Artifact storage
- [ ] Model loading
- [ ] Model validation
- [ ] Reproducible inference

# P2 - Architecture Decision Records

Create:

```text
docs/adr/
```

Examples:

```text
001-postgresql.md
002-redis.md
003-celery.md
004-temporal-validation.md
005-transaction-cost-model.md
006-execution-timing.md
007-model-selection.md
008-data-versioning.md
```

Each ADR:

```text
# Decision

## Problem

## Options

## Decision

## Reason

## Trade-offs

## Consequences
```

# P2 - Security

Review:

- [ ] Environment variables
- [ ] API authentication
- [ ] Authorization
- [ ] Secret management
- [ ] Input validation
- [ ] Dependency vulnerabilities
- [ ] SQL injection protection
- [ ] Rate limiting
- [ ] CORS
- [ ] Docker security

Run dependency/security scanning in CI.

# P2 - Docker

Target:

```text
docker compose up
```

Services:

```text
frontend
backend
postgres
redis
worker
monitoring
```

Document:

```bash
docker compose up --build
```

# P2 - CI/CD Architecture

Target:

```text
Git Push
   ↓
Lint
   ↓
Unit Tests
   ↓
Data Tests
   ↓
ML Tests
   ↓
Integration Tests
   ↓
Security Scan
   ↓
Docker Build
   ↓
Artifact
```

Optional:

```text
       ↓
Deployment
       ↓
Health Check
```

# P3 - Professional Research Dashboard

The UI should display actual research information.

Dashboard:

```text
Experiments
Models
Datasets
Backtests
Metrics
Risk
Research Reports
```

Experiment page:

```text
Experiment ID
Dataset
Model
Features
Parameters
Training Time
Metrics
Backtest
Risk
Comparison
```

Avoid decorative components that do not represent real data.

# P3 - Screenshots

Add real screenshots:

- [ ] Main dashboard
- [ ] Experiment comparison
- [ ] Backtest results
- [ ] Risk dashboard
- [ ] Model comparison
- [ ] Research report

# P3 - Demo Video

Create a 2-4 minute demo showing:

```text
1. Start system
2. Run experiment
3. Train/evaluate model
4. Compare models
5. Run backtest
6. Inspect risk
7. View results
```

# README Structure

Recommended:

```text
# AI Trading Research Platform

## Overview
## Why This Project Exists
## Architecture

## Engineering Capabilities
### ML Systems
### Backend Engineering
### Quantitative Research
### Risk Engineering

## Research Methodology
## Anti-Leakage Framework
## Benchmark Methodology
## Results
## Ablation Studies
## Statistical Analysis
## Backtesting
## API
## Infrastructure
## Testing
## CI/CD
## Reproducibility
## Limitations
## Future Work
## Project Structure
## Getting Started
```

# Evidence-Based Language

Avoid unsupported claims such as:

```text
Institutional-grade
Hedge-fund-grade
HFT-grade
100% uptime
Production-ready
State-of-the-art
Enterprise-grade
```

Prefer specific, verifiable statements:

```text
Temporal validation with embargo
Transaction-cost-aware backtesting
Automated leakage tests
Multi-asset benchmark suite
Reproducible ML experiments
Risk-control test suite
Containerized backend infrastructure
```

# Recruiter Evidence Matrix

| Recruiter Question | Evidence |
|---|---|
| Can he build ML pipelines? | `training/`, `features/`, experiment manifests |
| Does he understand leakage? | `tests/leakage/` |
| Can he evaluate models? | `evaluation/` |
| Does he understand quantitative research? | `RESEARCH.md`, ablation studies |
| Can he build backend systems? | FastAPI + PostgreSQL + Redis |
| Can he build distributed workers? | Celery |
| Can he test production systems? | `tests/` + CI |
| Does he understand deployment? | Docker + CI/CD |
| Does he understand observability? | Metrics + logs |
| Can he reproduce experiments? | manifests + dataset versions |
| Does he understand trading realism? | fees + slippage + execution timing |
| Does he understand risk? | `risk/` + risk tests |
| Can he explain engineering decisions? | ADRs |
| Does he understand failures? | Failure analysis |
| Can he communicate technical results? | Research reports |

# Final Repository Structure

```text
ai-trading-research-platform/
│
├── README.md
├── RESEARCH.md
├── RESULTS.md
├── SYSTEM_DOCUMENTATION.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── data/
│   ├── manifests/
│   └── validation/
│
├── features/
├── models/
├── training/
├── evaluation/
├── backtesting/
├── risk/
├── execution/
├── agents/
├── api/
├── services/
├── repositories/
│
├── tests/
│   ├── data/
│   ├── leakage/
│   ├── ml/
│   ├── backtest/
│   ├── risk/
│   ├── execution/
│   ├── api/
│   └── integration/
│
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── research/
│   └── FAILURE_ANALYSIS.md
│
├── load-tests/
├── observability/
├── scripts/
└── frontend/
```

# Final Acceptance Checklist

## P0

- [ ] CI green
- [ ] Flake8 fixed
- [ ] PyTest running in CI
- [ ] README local links fixed
- [ ] Virtual environment removed
- [ ] Temporary files removed
- [ ] Secrets removed
- [ ] `.gitignore` corrected

## P1

- [ ] Dataset versioning
- [ ] Experiment manifests
- [ ] Reproducible benchmarks
- [ ] Data validation
- [ ] Leakage tests
- [ ] Future candle mutation test
- [ ] Train-only scaler test
- [ ] Temporal split validation
- [ ] Embargo validation
- [ ] Transaction-cost tests
- [ ] Execution timing documented
- [ ] Benchmark methodology documented

## P2

- [ ] Ablation studies
- [ ] Statistical analysis
- [ ] Bootstrap confidence intervals
- [ ] Monte Carlo analysis
- [ ] Failure analysis
- [ ] Backend API quality
- [ ] Observability
- [ ] Load testing
- [ ] Security review
- [ ] Docker Compose
- [ ] CI/CD improvements
- [ ] Architecture Decision Records

## P3

- [ ] Professional dashboard
- [ ] Real screenshots
- [ ] Demo video
- [ ] Research visualization
- [ ] Polished README

# Definition of Done

The repository is upgraded when it provides verifiable evidence across all three target disciplines:

```text
                 ┌─────────────────────┐
                 │   ML SYSTEMS        │
                 │                     │
                 │ Data → Train → Eval │
                 │ Versioning → Model  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ BACKEND ENGINEERING │
                 │                     │
                 │ API → DB → Redis    │
                 │ Workers → Docker    │
                 │ CI/CD → Monitoring  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ QUANT RESEARCH      │
                 │                     │
                 │ Baselines           │
                 │ Walk-forward        │
                 │ Leakage controls    │
                 │ Costs + Slippage    │
                 │ Ablations           │
                 │ Statistics          │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ REPRODUCIBLE RESULT│
                 │                     │
                 │ Tests ✓             │
                 │ CI ✓                │
                 │ Benchmarks ✓        │
                 │ Documentation ✓     │
                 │ Evidence ✓          │
                 └─────────────────────┘
```

The final repository should allow a technically competent reviewer to inspect the implementation and independently verify the major claims.

# Core Principle

The objective is **not** to make the repository bigger.

The objective is to make it **harder to dismiss**.

The strongest signal is:

```text
Implementation
      +
Tests
      +
Measurements
      +
Experiments
      +
Reproducibility
      +
Failure Analysis
      +
Documentation
```

Not:

```text
More Models
+
More Agents
+
More Dashboards
+
More Buzzwords
```

The intended recruiter takeaway is:

> **This developer understands how to build ML systems, operate backend infrastructure, and conduct controlled quantitative experiments.**
