# Multi-Asset Universe Generalization Benchmark

**Audit Date:** October 2026  
**Asset Universe:** 13 Top-Liquidity Crypto Assets (`BTC`, `ETH`, `SOL`, `BNB`, `XRP`, `DOGE`, `ADA`, `AVAX`, `LINK`, `NEAR`, `LTC`, `DOT`, `SUI`)  
**Methodology:** Zero-leakage chronological evaluation with standardized 12 bps round-trip friction and identical hyperparameter configurations.

---

## 1. 13-Asset Multi-Model Performance Summary

| Symbol | Buy & Hold Return (%) | MA (20/50) Return (%) | Random Forest Return (%) | LightGBM Return (%) | Best Performing Model | Win Rate (LGBM) |
|---|---:|---:|---:|---:|---|---:|
| **BTCUSDT** | +0.13% | -3.27% | -0.51% | -2.12% | Buy & Hold (+0.13%) | 55.6% |
| **ETHUSDT** | +1.92% | +1.23% | 0.00% | -1.86% | Buy & Hold (+1.92%) | 72.7% |
| **SOLUSDT** | -4.64% | -5.12% | +0.45% | -1.15% | Random Forest (+0.45%) | 60.0% |
| **BNBUSDT** | +2.10% | -1.85% | -0.12% | -0.95% | Buy & Hold (+2.10%) | 50.0% |
| **XRPUSDT** | -6.40% | -8.10% | +1.20% | +0.85% | Random Forest (+1.20%) | 66.7% |
| **DOGEUSDT** | -8.25% | -12.40% | -2.10% | -3.45% | Random Forest (-2.10%) | 42.9% |
| **ADAUSDT** | -5.10% | -7.80% | -0.80% | -2.10% | Random Forest (-0.80%) | 45.5% |
| **AVAXUSDT** | -7.80% | -9.50% | +0.30% | -1.40% | Random Forest (+0.30%) | 58.3% |
| **LINKUSDT** | +0.85% | -2.10% | +0.15% | -0.65% | Buy & Hold (+0.85%) | 54.5% |
| **NEARUSDT** | -9.10% | -14.20% | -1.45% | -4.10% | Random Forest (-1.45%) | 38.5% |
| **LTCUSDT** | -1.20% | -4.50% | +0.10% | -1.10% | Random Forest (+0.10%) | 50.0% |
| **DOTUSDT** | -8.40% | -11.30% | -0.95% | -3.20% | Random Forest (-0.95%) | 41.7% |
| **SUIUSDT** | +5.40% | +2.80% | +1.80% | +0.40% | Buy & Hold (+5.40%) | 62.5% |

---

## 2. Cross-Asset Generalization Insights

1. **Asset Breadth & Dispersion:**
   - **Profitable Assets under LightGBM:** 2 / 13 (15.4%) — Only `XRPUSDT` and `SUIUSDT`.
   - **Profitable Assets under Random Forest:** 6 / 13 (46.2%) — Moderate cash-defense filtering.
   - **Profitable Assets under Buy & Hold:** 5 / 13 (38.5%).
2. **BTC Dominance Effect:**
   - Beta cross-correlation across altcoins during bear/sideways regimes causes simultaneous alpha degradation. Standalone single-asset signals without cross-sectional ranking fail to outperform cash.
3. **Volatility Drag on High-Beta Altcoins:**
   - High-beta altcoins (`NEAR`, `DOGE`, `DOT`) suffer disproportionately from whipsaw execution losses in 1h trend-following models.
