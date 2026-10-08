# System Architecture & Technical Specifications

## 1. High-Level Architecture Overview

The **AI Trading Research & Model Governance Platform** is structured into five decoupled, highly modular subsystems:

```mermaid
flowchart TD
    subgraph S1 [1. Research & Feature Layer]
        D1[Multi-Asset OHLCV Ingestion] --> D2[Point-in-Time Feature Pipeline]
        D2 --> D3[5-Fold Purged WFO Splitter]
        D3 --> D4[LightGBM Predictive Cross-Sectional Ranker]
    end

    subgraph S2 [2. Portfolio & Risk Engines]
        D4 --> P1[Top-2 Cross-Sectional Selector]
        P1 --> P2[Dynamic Risk Engine: Correlation Ceiling rho > 0.80]
        P2 --> P3[P3-1F Transaction Cost Engine: 21.38 bps base]
    end

    subgraph S3 [3. Order Management & Reliability Layer]
        P3 --> O1[Durable SQLite WAL OMS]
        O1 --> O2[Idempotent Order State Machine: SHA-256 Tokens]
        O2 --> O3[External Broker Adapter / FakeBroker Staging]
        O3 --> O4[Continuous 3-Way Portfolio Reconciler]
    end

    subgraph S4 [4. Model Intelligence & Drift Engine]
        D4 --> M1[Expected Calibration Error ECE & Brier Scorer]
        M1 --> M2[PSI, KS & Wasserstein Drift Detectors]
        M2 --> M3[Model Health Engine: HEALTHY, DEGRADED, DRIFTING]
    end

    subgraph S5 [5. Model Governance & Shadow Platform]
        M3 --> G1[Model Registry: SHA-256 Immutable Checksums]
        G1 --> G2[Isolated Shadow Evaluation Harness]
        G2 --> G3[10-Gate Hierarchical Promotion Engine]
        G3 --> G4[Atomic Champion Rollback Engine]
    end
```

---

## 2. Core Subsystem Responsibilities

### Subsystem 1: Research & Feature Pipeline
- Ingests canonical 13-asset OHLCV hourly data.
- Computes point-in-time features (volatility, momentum, volume ratios) fitted strictly on in-sample training folds.
- Implements 5-Fold Purged Walk-Forward Optimization with 24-bar embargo buffers to prevent temporal leakage.

### Subsystem 2: Portfolio & Risk Management
- Selects the Top-2 ranked assets on a 48-hour rebalancing cadence.
- Implements dynamic correlation ceilings ($\rho > 0.80$) and macro BTC regime conditioning (Bull, Sideways, Bear).
- Applies institutional-grade transaction cost friction (10 bps fee + 5 bps spread + 6.38 bps slippage = 21.38 bps one-way base).

### Subsystem 3: Execution Reliability & Order Management System (OMS)
- Backed by durable SQLite with Write-Ahead Logging (`PRAGMA synchronous=FULL`).
- Enforces deterministic SHA-256 client order ID tokens for 100% duplicate-execution prevention.
- Handles partial fills, timeouts, cancellation races, and crash recovery.
- Runs continuous 3-way reconciliation comparing internal OMS against external broker snapshots.

### Subsystem 4: Model Intelligence, Calibration & Drift
- Evaluates probability calibration via Brier Score and Expected Calibration Error ($\text{ECE} \le 0.08$).
- Detects feature and prediction distribution drift using Population Stability Index (PSI), Kolmogorov-Smirnov (KS) tests, and Wasserstein distance.
- Categorizes model operational health into 5 discrete states (`HEALTHY`, `DEGRADED`, `DRIFTING`, `UNRELIABLE`, `SUSPENDED`).

### Subsystem 5: Model Governance & Shadow Deployment
- Maintains an immutable Model Registry enforcing the Unique Champion Invariant ($\le 1$ active Champion per family).
- Runs candidate Challenger models in an isolated shadow execution harness with proven bitwise non-interference.
- Enforces a 10-Gate Fail-Closed Promotion Hierarchy requiring passing scores across artifact integrity, leakage checks, calibration, confidence, health, economics, risk limits, latency, shadow duration, and governance approvals.
- Provides atomic rollback to previous Champion versions with full audit trail persistence.
