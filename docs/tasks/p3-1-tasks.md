# P3-1 Implementation Tasks: Advanced Transaction Cost, Liquidity & Execution-Cost Intelligence

## Metadata
- **Epic**: P3-1 Advanced Execution Cost Intelligence
- **Status**: Ready for Execution
- **Target Branch**: `feature/p3-1-transaction-costs`
- **Universe**: 13 Canonical Assets (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `DOGEUSDT`, `ADAUSDT`, `AVAXUSDT`, `LINKUSDT`, `NEARUSDT`, `LTCUSDT`, `DOTUSDT`, `SUIUSDT`)
- **Strategy Invariant**: Frozen Long-Only Top-2, Equal-Weight 50/50, 48H Rebalance, 5-Fold Purged WFO

---

## Phase 1: Architecture & Data Availability Audit

- [x] **Task 1.1: Data Availability & Historical OHLCV Proxy Audit**
  - [x] Audit `data/{SYMBOL}_1h_historical.csv` for available columns (`open, high, low, close, volume, quote_asset_volume`).
  - [x] Formally document absence of historical L2/L3 order book data.
  - [x] Define point-in-time spread and slippage estimation proxies based strictly on past OHLCV data ($t \le \text{decision\_time}$).

- [x] **Task 1.2: Core Modular Cost Engine Architecture Design**
  - [x] Design modular structure separating fees, spread, slippage, market impact, liquidity, and execution delay.
  - [x] Define data contracts, configuration models, and trade attribution structures in `evaluation/transaction_costs.py`.

---

## Phase 2: Core Cost Engine Implementation (`evaluation/transaction_costs.py`)

- [x] **Task 2.1: Implement `FeeModel`**
  - [x] Support maker fee (e.g. 4 bps) and taker fee (e.g. 6 bps) configuration.
  - [x] Enforce strict distinction between one-way vs round-trip accounting.
  - [x] Support Decimal precision for exact monetary accounting.

- [x] **Task 2.2: Implement `SpreadModel`**
  - [x] Implement Corwin-Schultz 2-bar High-Low spread estimator using strictly past candles.
  - [x] Implement trailing volatility-volume fallback proxy: $\text{Spread}_{\text{bps}} = \alpha \cdot \frac{\sigma_{24h}}{\sqrt{\text{Volume}_{24h}}}$.
  - [x] Enforce zero-lookahead constraint (only historical candles $t \le T$ allowed).

- [x] **Task 2.3: Implement `SlippageModel`**
  - [x] Implement baseline slippage parameterized with volatility scaling:
    $$\text{Slippage}_{\text{bps}} = \text{base\_slippage} \cdot \left(1 + \beta_{\text{vol}} \cdot \frac{\sigma_{24h}}{\bar{\sigma}}\right) \cdot \left(1 + \beta_{\text{liq}} \cdot \frac{\bar{V}}{V_{24h}}\right)$$
  - [x] Add bounds to prevent negative or unbounded slippage.

- [x] **Task 2.4: Implement `MarketImpactModel`**
  - [x] Implement square-root participation model:
    $$\text{Impact}_{\text{bps}} = \gamma \cdot \sigma_{24h} \cdot \sqrt{\frac{\text{Order Notional}}{\text{Rolling 24H Quote Volume}}}$$
  - [x] Implement guards for illiquid bars and zero-volume edge cases.

- [x] **Task 2.5: Implement `LiquidityModel`**
  - [x] Compute trailing 24H rolling quote volume and turnover.
  - [x] Assign point-in-time liquidity scores (0–100) and classification (`HIGH`, `MEDIUM`, `LOW`, `EXTREME`).

- [x] **Task 2.6: Implement `DelayCostModel`**
  - [x] Model price drift between signal generation bar $t$ and execution bar $t+1$ open.
  - [x] Support configurable execution latency scenarios.

- [x] **Task 2.7: Implement `TransactionCostEngine` & Portfolio Integration**
  - [x] Combine all components without double-counting:
    $$\text{Total Cost} = \text{Fee} + \text{Spread Cost} + \text{Slippage Cost} + \text{Market Impact} + \text{Delay Cost}$$
  - [x] Integrate with portfolio rebalancer such that costs are evaluated per position adjustment $\Delta w_i = |w_{i,t} - w_{i,t-1}|$.

---

## Phase 3: Benchmark Experiments (`training/p3_1_cost_benchmark.py`)

- [x] **Task 3.1: EXP-P3-01-COST-001 (Fixed 12 bps Baseline)**
  - [x] Re-run canonical P1 strategy with 12 bps fixed cost model to verify baseline reproduction.
- [x] **Task 3.2: EXP-P3-01-COST-002 (Spread + Fee Model)**
  - [x] Evaluate strategy with empirical spread proxy and exchange fees.
- [x] **Task 3.3: EXP-P3-01-COST-003 (Spread + Slippage + Fee Model)**
  - [x] Add dynamic volatility-adjusted slippage to spread and fees.
- [x] **Task 3.4: EXP-P3-01-COST-004 (Full Advanced Cost Model)**
  - [x] Activate all 5 components (Fee, Spread, Slippage, Market Impact, Delay).
- [x] **Task 3.5: EXP-P3-01-COST-005 (Uncertainty Scenarios)**
  - [x] Run 4 scenarios: Optimistic, Base, Conservative, and Stressed.
- [x] **Task 3.6: EXP-P3-01-COST-006 (Asset-Level Sensitivity)**
  - [x] Break down costs asset-by-asset across all 13 canonical pairs.
- [x] **Task 3.7: EXP-P3-01-COST-007 (Rebalance Cadence Interaction)**
  - [x] Evaluate rebalance frequencies (18H, 24H, 36H, 48H) under realistic advanced cost dynamics.

---

## Phase 4: Empirical Attribution & Research Analysis

- [x] **Task 4.1: Asset-Level Cost Attribution**
  - [x] Calculate average cost (bps), P95 cost (bps), total turnover, and total cost contribution per asset.
  - [x] Rank assets from highest to lowest execution drag.
- [x] **Task 4.2: BTC Regime Cost Breakdown**
  - [x] Measure cost differences across Bull, Sideways, and Bear regimes.
- [x] **Task 4.3: Volatility & Liquidity Tier Profiling**
  - [x] Bucket trades by volatility quintiles and participation rate tiers.
- [x] **Task 4.4: 5-Fold WFO Fold Breakdown**
  - [x] Report Gross vs Net Return, Sharpe, Sortino, Calmar, and Drawdown for each fold.
- [x] **Task 4.5: Break-Even & Margin-of-Safety Analysis**
  - [x] Compute empirical break-even cost $C^*$ where Net Sharpe $= 0$.

---

## Phase 5: Automated Testing Suite & Validation

- [x] **Task 5.1: Unit Tests for Cost Engine (`tests/cross_sectional/test_p3_1_transaction_costs.py`)**
  - [x] Validate Fee, Spread, Slippage, Impact, Delay, and Total cost calculation.
  - [x] Verify zero double-counting.
- [x] **Task 5.2: Monotonicity Property Tests**
  - [x] Verify impact increases with trade size.
  - [x] Verify slippage increases with volatility.
  - [x] Verify cost increases as liquidity decreases.
- [x] **Task 5.3: Future Data Mutation & Zero-Lookahead Tests**
  - [x] Run test with mutated future OHLCV and confirm historical cost outputs remain bit-for-bit identical.
- [x] **Task 5.4: Determinism & Reproducibility Tests**
  - [x] Verify Run 1 vs Run 2 output bit-for-bit equality.
- [x] **Task 5.5: Full Repository Regression Verification**
  - [x] Run full paper trading suite (216 tests).
  - [x] Run full repository test suite (344 tests) across two successive runs.

---

## Phase 6: Documentation & Artifact Packaging

- [x] **Task 6.1: Generate Machine-Readable JSONs (`results/cost/`)**
  - [x] Export `p3_1_cost_comparison.json`, `p3_1_asset_costs.json`, `p3_1_regime_costs.json`, `p3_1_sensitivity.json`, and `p3_1_break_even.json`.
- [x] **Task 6.2: Package Experiment Artifacts (`artifacts/cost/`)**
  - [x] Package fold results, configuration manifests, and trade-level logs for `EXP-P3-01-COST-001` through `007`.
- [x] **Task 6.3: Author Comprehensive Research Document**
  - [x] Write `docs/research/p3-1-transaction-cost-intelligence.md` covering all 25 sections and answering research questions RQ1–RQ12.
