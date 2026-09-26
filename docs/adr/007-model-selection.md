# ADR 007: Tabular GBDT vs Deep Sequence Architectures

## Problem
Selecting the primary modeling architecture for crypto alpha generation across a multi-asset universe.

## Options
1. **End-to-End Deep Transformers**: High expressiveness, but vulnerable to overfitting in low SNR environments and computationally expensive.
2. **Gradient Boosted Decision Trees (LightGBM / CatBoost)**: Exceptional performance on tabular financial features, invariant to monotonic feature scaling, fast training, and built-in handling of missing values.
3. **Hybrid Setup**: LightGBM for cross-sectional ranking + shallow LSTM for sequential regime classification.

## Decision
Designate **LightGBM** as the primary cross-sectional production engine, supported by a 2-layer **LSTM** for temporal sequence baselines.

## Reason
Empirical benchmark suite showed LightGBM delivered the highest portfolio risk reduction (Max DD 6.54% vs 15.12% Buy & Hold) and superior out-of-sample stability compared to dense attention networks.

## Consequences
Faster training iteration cycles, lower inference latency, and higher empirical generalization across diverse market regimes.
