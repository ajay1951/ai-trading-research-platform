# P1-3: Volatility Parity & Risk-Managed Position Sizing

**Experiment Family:** `P1-3` (`EXP-CS-P13-EQ`, `EXP-CS-P13-IV`, `EXP-CS-P13-IV-CAP`, `EXP-CS-P13-COST`, `EXP-CS-P13-SOL`)  
**Audit Date:** October 2026  
**Auditor Profile:** Senior Quantitative Researcher & Risk Systems Verification Specialist  
**Frozen Baseline:** 48H Cross-Sectional Long-Only Top-2 Momentum Strategy (`EXP-CS-RB-001` / `P1-2F`).  
**Evaluated Methods:**
1. **Strategy A (Control):** Equal Weight 50% / 50% Baseline (`EXP-CS-P13-EQ`).
2. **Strategy B:** Inverse Volatility Weighting ($w_i = (1/\sigma_i) / \sum(1/\sigma_j)$) (`EXP-CS-P13-IV`).
3. **Strategy C:** Inverse Volatility + Position Cap ($w_i \in [25\%, 75\%]$) (`EXP-CS-P13-IV-CAP`).

---

## 1. Objective

The objective of P1-3 is to determine whether predefined volatility-aware position sizing improves the risk characteristics of the validated 48H cross-sectional Long-Only Top-2 strategy without introducing lookahead leakage, excessive turnover, transaction cost drag, or post-hoc parameter optimization.

This is a **risk-management and audit investigation**, not a return-maximization experiment.

---

## 2. Frozen Experimental Setup

All research parameters from the validated P1-2F baseline remain frozen:
- **Asset Universe:** 13 liquid perpetual pairs (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `DOGEUSDT`, `ADAUSDT`, `AVAXUSDT`, `LINKUSDT`, `SUIUSDT`, `NEARUSDT`, `DOTUSDT`, `LTCUSDT`).
- **Validation Scheme:** 5-fold Purged Walk-Forward Optimization (WFO), 12,000 hourly bars total (~500 days), ~1 month test period per fold.
- **Embargo:** 24-bar purged boundary gap between train and test splits.
- **Ranking Engine:** LightGBM regressor predicting forward return relative strength.
- **Selection:** Long-Only Top-2 assets ranked at each rebalance.
- **Rebalance Frequency:** 48 hours (48 bars). Intermediate bars hold weights constant.
- **Execution Timing:** $t+1$ execution (signals formed at candle close $t$, executed at $t+1$).
- **Friction Model:** 12.0 bps round-trip baseline (4.0 bps maker fee + 2.0 bps slippage per side).

---

## 3. Sizing Methods

### Strategy A: Equal Weight (Control)
$$w_i = 0.50, \quad w_j = 0.50$$

### Strategy B: Inverse Volatility
Realized volatility $\sigma_i$ is computed using a rolling 168-hour (7-day) lookback on hourly log returns:
$$\sigma_{i, t} = \text{std}(\ln(p_t / p_{t-1}))_{[t-168:t]} \times \sqrt{24 \times 365}$$
Weights are normalized across the Top 2 active assets:
$$w_i = \frac{1 / \sigma_i}{\sum_{j=1}^2 1 / \sigma_j}$$

### Strategy C: Inverse Volatility + Position Cap
The normalized inverse-volatility weights are strictly clipped to $[25\%, 75\%]$:
$$w_1^{\text{capped}} = \text{clip}(w_1, 0.25, 0.75), \quad w_2^{\text{capped}} = 1.0 - w_1^{\text{capped}}$$
Ensuring $\sum w_i = 1.0$ and $0.25 \le w_i \le 0.75$ on all active allocations.

---

## 4. Leakage Controls & Causal Integrity

Passed point-in-time and future-mutation leakage tests with no detected lookahead leakage:
- **Point-in-Time Realized Volatility:** Volatility calculated at timestamp $t$ utilizes strictly closed candles up to bar $t$.
- **Future Mutation Invariance:** Mutating price data at $t > 150$ leaves volatility and position sizing prior to $t=150$ bit-for-bit identical.
- **Ranking Independence:** Sizing is applied strictly downstream of the frozen ranking engine without feedback into feature calculation or model scoring.
- **No Intermediate Rebalances:** Weights remain locked across intermediate bars within the 48-hour cadence.

---

## 5. Cap Implementation & Audit of the 75.72% Discrepancy

### Root Cause Analysis:
During the P1-3 audit, an apparent inconsistency was investigated where `BTCUSDT` showed a maximum weight of `75.72%` alongside the capped strategy specification.
- **Finding:** The sizing engine (`evaluation/volatility_sizing.py`) had correctly implemented the `[0.25, 0.75]` clipping for Strategy C (`mode="iv_capped"`).
- **Cause:** The `75.72%` figure was the maximum raw weight generated under **Strategy B (uncapped Inverse Volatility)** during Fold 2 on `BTCUSDT` (when paired with `NEARUSDT`). In the previous exposure summary table, the column `IV Max Weight (%)` displayed the uncapped Strategy B maximum without distinguishing it from the Strategy C capped maximum.
- **Resolution:** The reporting infrastructure now explicitly reports both `iv_raw_max_weight_pct` and `iv_cap_max_weight_pct`. The maximum final weight under Strategy C is verified to be strictly bounded at `75.00%`.

---

## 6. Cap Activation Statistics

Deterministic diagnostics across all 75 rebalance events (5 WFO folds) yield:

```text
=============================================================================
CAP DIAGNOSTIC METRIC                         VALUE
=============================================================================
Total Rebalance Events                        75
Cap Activation Count                          1
Cap Activation Rate                           1.33%
Upper Cap Hits (Weight > 75%)                 1
Lower Cap Hits (Weight < 25%)                 1
Maximum Raw IV Weight                         75.72% (BTCUSDT, Fold 2)
Minimum Raw IV Weight                         24.28% (NEARUSDT, Fold 2)
Maximum Final IV-Cap Weight                   75.00%
Minimum Final IV-Cap Weight                   25.00%
Binding Status                                Binding on 1 event (1.33%)
=============================================================================
```

**Interpretation:** The 25%-75% cap was largely non-binding over the evaluated sample (active on only 1 out of 75 rebalance events), which explains why Strategy B (uncapped IV) and Strategy C (IV-Cap) produce virtually identical backtest results.

---

## 7. Fold-Level Results

| Fold | Test Period | EQ Return (%) | IV Return (%) | IV-Cap Return (%) | EQ Sharpe | IV Sharpe | IV-Cap Sharpe | EQ Max DD (%) | IV Max DD (%) | IV-Cap Max DD (%) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Fold 1** | 2025-06-08 → 2025-07-07 | +15.81% | +17.35% | +17.30% | +3.43 | +3.86 | +3.85 | 17.50% | 16.97% | 16.97% |
| **Fold 2** | 2025-07-09 → 2025-08-07 | +23.25% | +24.89% | +24.89% | +4.44 | +4.72 | +4.72 | 14.87% | 14.15% | 14.15% |
| **Fold 3** | 2025-08-09 → 2025-09-07 | +7.98% | +4.69% | +4.69% | +1.82 | +1.24 | +1.24 | 12.24% | 13.55% | 13.55% |
| **Fold 4** | 2025-09-08 → 2025-10-07 | +20.97% | +18.67% | +18.67% | +4.62 | +4.29 | +4.29 | 11.00% | 12.70% | 12.70% |
| **Fold 5** | 2025-10-09 → 2025-11-07 | +21.83% | +17.24% | +17.24% | +3.94 | +3.31 | +3.31 | 11.29% | 11.13% | 11.13% |
| **Mean** | — | **+17.97%** | **+16.57%** | **+16.56%** | **+3.65** | **+3.48** | **+3.48** | **13.38%** | **13.70%** | **13.70%** |

---

## 8. Aggregate Performance Summary

| Strategy | Sizing Mode | Mean Net Return (%) | Median Net Return (%) | Mean Gross Return (%) | Friction Drag (%) | Mean Sharpe | Mean Sortino | Max DD (%) | Calmar Ratio | Daily Turnover | Profitable Folds | Worst Fold Ret (%) | Best Fold Ret (%) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| **Equal Weight (Control)** | `equal` | **+17.97%** | **+20.97%** | **+19.71%** | 1.74% | **+3.65** | **+5.63** | **13.38%** | **17.00** | **1.006x** | **5/5** | **+7.98%** | +23.25% |
| **Inverse Volatility** | `inverse_vol` | +16.57% | +17.35% | +18.33% | 1.76% | +3.48 | +5.28 | 13.70% | 15.31 | 1.017x | 5/5 | +4.69% | **+24.89%** |
| **IV Capped [25%, 75%]** | `iv_capped` | +16.56% | +17.30% | +18.32% | 1.76% | +3.48 | +5.28 | 13.70% | 15.30 | 1.017x | 5/5 | +4.69% | **+24.89%** |

---

## 9. Risk Metrics & Accurate Risk Interpretation

- **Measured Annualized Portfolio Volatility:**
  - Equal Weight: **55.34%**
  - Inverse Volatility: **53.48%** (-1.86 percentage points)
  - IV Capped: **53.49%**
- **Accurate Risk Interpretation:**
  > Inverse-volatility sizing reduced measured annualized portfolio volatility by approximately 1.86 percentage points, but this reduction did not translate into improved maximum drawdown or risk-adjusted performance. Equal weighting remained superior on return (+17.97% vs +16.57%), Sharpe ratio (3.65 vs 3.48), Sortino ratio (5.63 vs 5.28), Calmar ratio (17.00 vs 15.31), and worst-fold return (+7.98% vs +4.69%).

---

## 10. Turnover and Transaction Costs

- **Friction Drag:** 1.74% (Equal Weight) vs 1.76% (Inverse Volatility).
- **Daily Turnover:** 1.006x (Equal Weight) vs 1.017x (Inverse Volatility).
- Sizing adjustments at rebalance points introduced minimal additional turnover (+0.011x daily) because rebalancing occurs at the 48-hour boundary.

---

## 11. SOL Sensitivity Analysis

| Strategy | Full Universe Return (%) | Full Sharpe | Full Max DD (%) | No-SOL Return (%) | No-SOL Sharpe | No-SOL Max DD (%) | SOL $\Delta$ Return |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Equal Weight** | **+17.97%** | **+3.65** | **13.38%** | **+20.84%** | **+3.94** | 13.84% | -2.87% |
| **Inverse Vol** | +16.57% | +3.48 | 13.70% | +18.89% | +3.69 | 13.96% | -2.32% |
| **IV Capped** | +16.56% | +3.48 | 13.70% | +18.88% | +3.69 | 13.96% | -2.32% |

---

## 12. Transaction Cost Sensitivity

| Cost Scenario | Fee + Slippage | Equal Weight Net Ret (%) | Equal Weight Sharpe | IV Net Ret (%) | IV Sharpe | IV-Cap Net Ret (%) | IV-Cap Sharpe |
|---|---|---:|---:|---:|---:|---:|---:|
| **Zero Cost** | 0.0 bps | +20.04% | +3.99 | +18.64% | +3.84 | +18.63% | +3.83 |
| **Baseline** | 12.0 bps | **+17.97%** | **+3.65** | **+16.57%** | **+3.48** | **+16.56%** | **+3.48** |
| **Adverse** | 20.0 bps | +16.61% | +3.42 | +15.20% | +3.25 | +15.19% | +3.24 |

---

## 13. IV vs IV-Cap Analysis

The backtest performance of Strategy B (IV) and Strategy C (IV-Cap) is almost identical (+16.57% vs +16.56% return, 3.48 Sharpe for both).
- **Reason:** Across the 5 folds (75 rebalance decisions), the raw IV weight exceeded the 75% cap on only **1 occasion (1.33% activation rate)** in Fold 2 (`BTCUSDT` raw weight 75.72%, capped to 75.00%).
- Because the cap was binding on only 1.33% of decisions with a minor 0.72% truncation, the capped and uncapped strategies produced nearly indistinguishable trajectory and risk outcomes.

---

## 14. Documented Limitations

1. **Window Selection:** The 168-hour rolling volatility window was predefined to avoid lookahead optimization; other lookback windows were not evaluated to preserve research integrity.
2. **Asset Concentration:** In 2-asset portfolios, inverse volatility heavily favors large-cap crypto (`BTCUSDT` average active weight 67.85%), which dampens high-beta momentum outperformance.
3. **Execution Realism:** Execution is simulated at $t+1$ with 12 bps fixed friction. Real-world fill rates in extreme market dislocations may differ.

---

## 15. Final Research Decision

```text
=============================================================================
PRIMARY STRATEGY:
48H Cross-Sectional Long-Only Top-2 (Equal Weight 50% / 50%)
- Higher net return (+17.97% vs +16.57%)
- Superior risk-adjusted returns (Sharpe 3.65 vs 3.48, Sortino 5.63 vs 5.28)
- Superior drawdown and recovery (Calmar 17.00 vs 15.31)
- Higher worst-fold return (+7.98% vs +4.69%)
- Simpler, parameter-free allocation mechanism

SECONDARY / CONSERVATIVE EXPERIMENT:
Inverse Volatility Weighting (EXP-CS-P13-IV / EXP-CS-P13-IV-CAP)
- Validated conservative profile for mandates requiring lower realized portfolio volatility (53.48% vs 55.34%).
=============================================================================
```

---

## 16. Reproducibility

To reproduce these exact results:
```bash
# 1. Run unit and regression tests
pytest -q tests/cross_sectional/test_p13_volatility_sizing.py

# 2. Run the P1-3 benchmark suite
python training/p13_volatility_benchmark.py
```
All outputs are exported deterministically to `results/cross_sectional/p1_3_volatility_sizing.json` and `artifacts/cross_sectional/`.
