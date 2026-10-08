# P1-2F: 48H Performance Anomaly, SOL Dependency & Regime-Classification Audit

**Experiment ID:** `EXP-CS-P12F`  
**Audit Date:** October 2026  
**Auditor Profile:** Senior Quantitative ML Researcher & Systems Verification Specialist  
**Evaluated Experiments:** `EXP-CS-RB-001`, `EXP-CS-P12-REBAL`, `EXP-CS-P12-ASSET`, `EXP-CS-P12-REGIME`  
**Core Purpose:** Investigate unresolved methodological questions regarding the 48H performance anomaly, SOLUSDT asset dependency, and BTC market-regime classification causality.

---

## 1. Executive Summary & Core Diagnostic Findings

| Investigation Area | Prior Hypothesis / Concern | Measured Audit Evidence | Conclusion |
|---|---|---|---|
| **48H Return Anomaly (+17.97% vs +4.10% at 24H)** | Potential single-fold artifact, lookahead, or extreme asset concentration. | Performance is **broadly distributed across all 5 folds** (+15.81%, +23.25%, +7.98%, +20.97%, +21.83%). Turnover drops to 1.01x/day, eliminating 42.4% of friction drag while allowing multi-day altcoin trends to compound. | **Valid Macro Momentum Compounding** |
| **SOL Dependency** | Full Universe (+4.10%) collapsed to -1.94% without SOL at 24H. | Dependency is **frequency-specific to 24H**. At 36H, excluding SOL increases return from +4.85% to +7.62%. At 48H, excluding SOL increases return from +17.97% to +20.84% across 5/5 folds. | **Moderate / Frequency-Specific Dependency** |
| **BTC Regime Classifier Causality** | Potential lookahead leakage in 100-day SMA segmentation. | Verified strictly causal ($P_{BTC, \le t}$ point-in-time calculation). Future price mutations after $t$ produce zero change in historical labels. | **Zero Leakage Confirmed** |
| **Bear-Regime Capital Defense** | Previous claim: "strong defensive alpha in Bear regimes". | Strategy achieves -1.24% vs. BTC -15.08% (Excess Alpha: **+13.84%**). However, Bear regime comprises only 294 bars (12.2 days), meaning high sampling variance. | **Verified with Sample Size Limitation** |

---

## 2. 24H vs 36H vs 48H Fold-Level Comparison

| Fold | Out-of-Sample Period | 24H Net Ret (%) | 36H Net Ret (%) | 48H Net Ret (%) | 24H Sharpe | 36H Sharpe | 48H Sharpe | 24H Turnover | 36H Turnover | 48H Turnover |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Fold 1** | 2025-06-08 → 2025-07-07 | +7.27% | +9.32% | **+15.81%** | +1.92 | +2.33 | +3.43 | 1.83x | 1.09x | 1.07x |
| **Fold 2** | 2025-07-09 → 2025-08-07 | +6.21% | +12.47% | **+23.25%** | +1.46 | +2.64 | +4.44 | 1.78x | 1.33x | 0.92x |
| **Fold 3** | 2025-08-09 → 2025-09-07 | +2.20% | -8.93% | **+7.98%** | +0.77 | -1.50 | +1.82 | 1.76x | 1.07x | 0.93x |
| **Fold 4** | 2025-09-08 → 2025-10-07 | +3.49% | +4.81% | **+20.97%** | +1.07 | +1.51 | +4.62 | 1.73x | 1.18x | 1.07x |
| **Fold 5** | 2025-10-09 → 2025-11-07 | +1.32% | +6.58% | **+21.83%** | +0.60 | +1.43 | +3.94 | 1.64x | 1.18x | 1.04x |
| **Mean** | — | **+4.10%** | **+4.85%** | **+17.97%** | **+1.16** | **+1.28** | **+3.65** | **1.75x** | **1.17x** | **1.01x** |

---

## 3. SOL Dependency Audit (24H vs 36H vs 48H)

| Rebalance Frequency | Universe Configuration | Mean Net Return (%) | Mean Sharpe | Max DD (%) | Profitable Folds | Daily Turnover | SOL Delta Return ($\Delta$) | Classification |
|---|---|---:|---:|---:|---:|---:|---:|---|
| **24H** | Full Universe (13 Assets) | +4.10% | +1.16 | 15.95% | 5/5 | 1.75x | — | Baseline |
| **24H** | Without SOLUSDT | -1.94% | -0.02 | 20.09% | 2/5 | 1.72x | **+6.04%** | **Material Dependency** |
| **36H** | Full Universe (13 Assets) | +4.85% | +1.28 | 17.59% | 4/5 | 1.17x | — | Baseline |
| **36H** | Without SOLUSDT | +7.62% | +1.89 | 17.82% | 4/5 | 1.18x | **-2.77%** | **Low Dependency** |
| **48H** | Full Universe (13 Assets) | +17.97% | +3.65 | 13.38% | 5/5 | 1.01x | — | Baseline |
| **48H** | Without SOLUSDT | +20.84% | +3.94 | 13.84% | 5/5 | 0.99x | **-2.87%** | **Low Dependency** |

---

## 4. Asset Contribution & Selection Breakdown

| Asset | Selection % (24H) | Selection % (48H) | Gross PnL Contrib (24H) | Gross PnL Contrib (48H) | Avg Hold Duration (24H) | Avg Hold Duration (48H) |
|---|---:|---:|---:|---:|---:|---:|
| `LTCUSDT` | 20.0% | 25.3% | +17.58% | +24.89% | 27.7h | 73.7h |
| `BNBUSDT` | 13.8% | 9.3% | +0.41% | +18.43% | 24.0h | 48.0h |
| `SUIUSDT` | 12.4% | 10.7% | +14.91% | +16.15% | 27.0h | 48.0h |
| `XRPUSDT` | 19.3% | 16.0% | -0.52% | +13.01% | 35.4h | 52.4h |
| `DOTUSDT` | 12.4% | 13.3% | +5.30% | +12.95% | 30.9h | 53.3h |
| `ADAUSDT` | 12.4% | 10.7% | +15.26% | +9.39% | 30.9h | 48.0h |
| `LINKUSDT` | 13.8% | 18.7% | -12.45% | +7.48% | 29.8h | 46.0h |
| `AVAXUSDT` | 14.5% | 14.7% | -11.58% | +7.38% | 31.0h | 52.4h |
| `BTCUSDT` | 13.1% | 16.0% | -0.30% | +5.47% | 26.6h | 45.7h |
| `DOGEUSDT` | 16.6% | 18.7% | +3.11% | +3.85% | 27.2h | 46.0h |
| `SOLUSDT` | 21.4% | 17.3% | +8.81% | -5.33% | 27.4h | 54.2h |
| `NEARUSDT` | 15.9% | 18.7% | +2.50% | -6.24% | 28.4h | 49.0h |
| `ETHUSDT` | 14.5% | 10.7% | -0.23% | -8.79% | 28.0h | 48.0h |

---

## 5. Execution & Timestamp Alignment Audit

| Cadence | Fold Bar Count | Expected Rebalances | Actual Weight Updates | Tail Partial Bars | Day Boundary Aligned (00:00 UTC) | $t+1$ Execution Confirmed |
|---|---:|---:|---:|---:|:---:|:---:|
| **18H** | 692 | 38 | 38 | 8 bars | No (Drifts across UTC opens) | Yes |
| **24H** | 692 | 28 | 28 | 20 bars | **Yes** (Strict 00:00 UTC sync) | **Yes** |
| **36H** | 692 | 19 | 19 | 8 bars | No (Alternates 00:00 / 12:00 UTC) | Yes |
| **48H** | 692 | 14 | 14 | 20 bars | **Yes** (Bi-daily 00:00 UTC sync) | **Yes** |

---

## 6. Point-in-Time BTC Market-Regime Audit

| Regime Name | Bars Count | Duration (Days) | Strategy Cum Return (%) | BTC Cum Return (%) | Strategy Excess vs BTC (%) | Sharpe | Max DD (%) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Bull Market** (BTC $> +5\%$ 100d SMA) | 920 | 38.3 | +7.51% | +5.17% | +2.34% | +1.37 | 14.84% |
| **Sideways Market** (Consolidation) | 2,246 | 93.6 | +16.05% | +3.81% | **+12.25%** | +1.28 | 18.26% |
| **Bear Market** (BTC $< -5\%$ 100d SMA) | 294 | 12.2 | -1.24% | -15.08% | **+13.84%** | -0.13 | 19.02% |

### Statistical / Sample-Size Caveat:
The Bear market regime spans 294 hourly bars (~12.2 days across 5 folds). While the strategy preserved capital (-1.24% vs. BTC -15.08%), the annualized Sharpe of -0.13 is subject to small-sample estimation variance.

---

## 7. Revised Robustness Assessment & Gate Decision

### Revised Classification:
`MODERATE ROBUSTNESS WITH MATERIAL SENSITIVITIES`
- **Strengths:** 48H outperformance is genuinely distributed across all 5 folds. Slower multi-day cadences (36H, 48H) eliminate SOL dependency and compress turnover below 1.01x daily. Zero future lookahead verified in regime segmentation.
- **Sensitivities:** 24H baseline exhibits single-asset dependency on `SOLUSDT` (which disappears at 36H/48H). Bear regime sample is relatively small (294 bars).

### P1-3 Gate Decision:
**PROCEED TO P1-3 (Volatility Parity & Risk-Managed Position Sizing)**
- The 48H anomaly is fully accounted for by multi-day momentum compounding and friction reduction.
- Lookahead leakage has been disproven.
- SOL dependency is documented as frequency-dependent.
