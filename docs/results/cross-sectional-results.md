# Cross-Sectional Multi-Asset Momentum Ranking Research Report

**Experiment ID:** `EXP-CS-001`  
**Evaluation Scope:** 5-Fold Purged Walk-Forward Cross-Validation across the 13-Asset Crypto Universe  
**Universe Assets (13):** `BTC`, `ETH`, `SOL`, `BNB`, `XRP`, `DOGE`, `ADA`, `AVAX`, `LINK`, `NEAR`, `LTC`, `DOT`, `SUI`  
**Execution Frictions:** 4 bps maker fee + 2 bps slippage per fill (12 bps round-trip per 100% turnover)  
**Execution Timing:** $t+1$ bar open execution on standardized 1h bars.

---

## 1. Strategy Comparison Matrix

| Strategy | Mean Fold Return (%) | Mean Fold Sharpe | Mean Fold Max DD (%) | Profitable Folds | Strategy Behavior |
|---|---:|---:|---:|:---:|---|
| **Equal-Weight Buy & Hold (13 Assets)** | **-1.26%** | **+0.07** | **18.55%** | **2 / 5 (40%)** | Passive universe benchmark |
| **Single-Asset Baseline (BTC LightGBM)** | **-8.44%** | **-2.13** | **12.88%** | **1 / 5 (20%)** | Single-asset directional 1h model |
| **Cross-Sectional Long-Only (Top 2)** | **-27.27%** | **-5.61** | **33.92%** | **0 / 5 (0%)** | Long top-2 relative strength runners |
| **Cross-Sectional Long/Short (Top 2 / Bottom 2)** | **-48.69%** | **-12.27** | **51.38%** | **0 / 5 (0%)** | Long top-2 / Short bottom-2 momentum |

---

## 2. Walk-Forward Fold-Level Breakdown

| Fold | OOS Test Period | Bars | CS Long/Short Return (%) | CS Long/Short Sharpe | CS Long-Only Return (%) | BnH Universe Return (%) |
|---|---|---:|---:|---:|---:|---:|
| **Fold 1** | 2025-06-08 to 2025-07-07 | 692 | -42.25% | -10.74 | -23.94% | -6.12% |
| **Fold 2** | 2025-07-09 to 2025-08-07 | 692 | -40.55% | -8.16 | -5.42% | +18.97% |
| **Fold 3** | 2025-08-09 to 2025-09-07 | 692 | -51.90% | -14.37 | -29.68% | -1.51% |
| **Fold 4** | 2025-09-08 to 2025-10-07 | 692 | -56.52% | -17.96 | -30.15% | +6.04% |
| **Fold 5** | 2025-10-09 to 2025-11-07 | 692 | -52.24% | -10.10 | -47.18% | -23.68% |

---

## 3. Empirical Research Findings

1. **High Rebalancing Turnover vs. Execution Frictions:**
   - The hourly cross-sectional model rebalances positions almost every hour as predicted probability ranks fluctuate.
   - High turnover ($>150\%$ daily) compounding 12 bps round-trip friction causes rapid performance decay (-48.69% per fold).
2. **Short-Side Volatility Squeeze:**
   - Shorting high-beta altcoins in the bottom-2 bucket (`DOGE`, `NEAR`, `SUI`) during broad crypto relief rallies results in severe asymmetric drawdowns.
3. **Turnover Reduction is Mandatory for Cross-Sectional Feasibility:**
   - For cross-sectional momentum to be viable in crypto markets, rebalancing horizons must be shifted from **hourly to 4h/24h intervals**, or hysteresis buffer bands must be applied before triggering portfolio rotation.
