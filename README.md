# AI Trading Research Platform & Quantitative Workstation

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16.3-black.svg)](https://nextjs.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-ee4c2c.svg)](https://pytorch.org/)
[![Tests](https://img.shields.io/badge/tests-22%20passed-brightgreen.svg)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A rigorous quantitative research and machine learning engineering platform for cryptocurrency market microstructure. Designed with strict prevention of data leakage, causal point-in-time feature engineering, empirical baseline benchmarking across 13 liquid assets, and an autonomous Next.js trading workstation.

---

## 1. Project Overview & Problem Statement

Most algorithmic trading repositories suffer from severe methodological flaws:
1. **Lookahead Bias & Data Leakage**: Inadvertently scaling features on future test distributions or using forward returns as input signals.
2. **Evaluation in a Vacuum**: Reporting deep learning / Transformer metrics without comparing against classical baselines (Buy & Hold, Moving Average, Logistic Regression, Random Forest, LightGBM).
3. **Frictionless Delusions**: Ignoring exchange fees (0.04% taker) and execution slippage (0.02%), producing high-churn strategies that collapse in live execution.

This platform addresses these challenges by enforcing **automated leakage prevention tests**, **purged walk-forward temporal splitting**, **cryptographic dataset manifests**, and **empirical, multi-asset evidence-backed evaluation**.

---

## 2. Multi-Asset Portfolio Benchmark Results (13 Assets)

All results are empirically measured on an identical out-of-sample chronological test set under **0.04% maker/taker fees + 0.02% slippage per fill (12 bps round-trip)** across all 13 universe assets (`BTC`, `ETH`, `SOL`, `BNB`, `XRP`, `DOGE`, `ADA`, `AVAX`, `LINK`, `NEAR`, `LTC`, `DOT`, `SUI`).

| Model Architecture | Portfolio Return (%) | Average Sharpe | Average Max DD (%) | Total Trades | Average Win Rate (%) | Average Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **LightGBM (GBDT)** | **+3.05%** | **+0.14** | **6.54%** | **477** | **59.32%** | **1.93** |
| **Buy & Hold (Equal-Weight Universe)** | -0.23% | -0.12 | 15.12% | 13 | 53.85% | 53.31 |
| **Random Forest (100 Trees)** | -0.59% | -0.20 | **4.20%** | 175 | 50.18% | 5.21 |
| **Moving Average (20/50 SMA)** | -4.07% | -1.39 | 12.33% | 87 | 36.63% | 1.11 |

*Key finding: Machine learning filtering (LightGBM) generated a net positive return (+3.05%) while cutting portfolio maximum drawdown by more than half (6.54% vs Buy & Hold's 15.12%) during a difficult market regime.*

---

## 2. System Architecture

```mermaid
graph TD
    subgraph Data Pipeline [1. Data Engineering & Integrity]
        RawData[(Binance OHLCV Data)] --> Validator[Data Quality Validator]
        Validator --> Manifest[SHA-256 Dataset Manifest]
        Manifest --> Splitter[Purged Temporal Splitter]
    end

    subgraph Feature Engine [2. Point-in-Time Features]
        Splitter --> PriceFeat[Price & Returns]
        Splitter --> VolFeat[Parkinson & ATR Volatility]
        Splitter --> MomFeat[RSI, MACD & Donchian]
        Splitter --> VoluFeat[VWAP & Volume Z-Scores]
        PriceFeat & VolFeat & MomFeat & VoluFeat --> CausalMatrix[Causal Feature Matrix]
    end

    subgraph Benchmark Suite [3. Quantitative Modeling]
        CausalMatrix --> BnH[Buy & Hold]
        CausalMatrix --> Classical[Logistic Reg / Random Forest]
        CausalMatrix --> GBDT[LightGBM Gradient Boosting]
        CausalMatrix --> Deep[PyTorch LSTM & Transformer]
    end

    subgraph Execution & Monitoring [4. Execution & Workstation]
        Deep --> RiskEngine[Risk Manager & Slot Limits]
        RiskEngine --> LiveDaemon[Candle-Close Execution Daemon]
        LiveDaemon <--> LiveState[(live_state.json)]
        LiveState --> WorkstationUI[Next.js Quantitative Workstation]
    end

    style Data Pipeline fill:#121620,stroke:#2a3346,color:#e2e8f0
    style Feature Engine fill:#121620,stroke:#2a3346,color:#e2e8f0
    style Benchmark Suite fill:#121620,stroke:#2a3346,color:#e2e8f0
    style Execution & Monitoring fill:#121620,stroke:#2a3346,color:#e2e8f0
```

---

## 3. Measured Experimental Results

All results are empirically measured on an identical out-of-sample chronological test set (1,146 hours) under **0.04% maker/taker fees + 0.02% slippage per fill (12 bps round-trip)**.

| Model Architecture | Return (%) | Sharpe Ratio | Sortino Ratio | Max Drawdown (%) | Calmar Ratio | Trades | Win Rate (%) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Random Forest (100 Trees)** | **+1.12%** | **3.77** | **559.97** | **0.10%** | **10.76** | 4 | **100.0%** | **99.00** |
| **PyTorch LSTM (2-Layer)** | **+4.27%** | **1.67** | **1.40** | **4.73%** | **0.90** | 30 | **66.7%** | **2.55** |
| **Buy & Hold (Passive Index)** | **+2.56%** | **0.70** | **0.90** | **11.11%** | **0.23** | 1 | 100.0% | 99.00 |
| **Transformer (Attention)** | -0.48% | -0.12 | -0.09 | 3.89% | -0.12 | 50 | 46.0% | 1.77 |
| **Logistic Regression** | -2.71% | -2.05 | -0.64 | 4.19% | -0.65 | 18 | 50.0% | 0.90 |
| **LightGBM** | -2.57% | -2.07 | -0.91 | 5.10% | -0.50 | 30 | 53.3% | 1.18 |
| **Moving Average (20/50 SMA)** | -8.53% | -2.72 | -2.83 | 12.55% | -0.68 | 13 | 38.5% | 0.56 |
| **Random Baseline** | -31.01% | -11.72 | -14.53 | 31.69% | -0.98 | 281 | 52.7% | 1.08 |

*Full methodology and ablation breakdowns are documented in [RESEARCH.md](file:///c:/Users/ajayg/ai_crypto_bot/RESEARCH.md) and [RESULTS.md](file:///c:/Users/ajayg/ai_crypto_bot/RESULTS.md).*

---

## 4. Data Leakage Prevention Guarantee

To guarantee scientific integrity, the test suite enforces automated checks:

* **Lookahead Bias Prevention** ([tests/test_no_lookahead.py](file:///c:/Users/ajayg/ai_crypto_bot/tests/test_no_lookahead.py)): Mutating future candles ($t+1 \dots T$) causes zero variation in features calculated at time $t$.
* **Scaler Leakage Prevention** ([tests/test_feature_leakage.py](file:///c:/Users/ajayg/ai_crypto_bot/tests/test_feature_leakage.py)): Scalers are fitted *strictly* on training folds.
* **Label Separation** ([tests/test_label_leakage.py](file:///c:/Users/ajayg/ai_crypto_bot/tests/test_label_leakage.py)): Target forward returns cannot appear in input feature space.
* **Temporal Boundaries** ([tests/test_temporal_split.py](file:///c:/Users/ajayg/ai_crypto_bot/tests/test_temporal_split.py)): Enforces chronological order with an embargo buffer between folds.
* **Transaction Cost Verification** ([tests/test_transaction_costs.py](file:///c:/Users/ajayg/ai_crypto_bot/tests/test_transaction_costs.py)): Ensures fees and slippage are deducted on every execution.

Run the verification test suite:
```bash
pytest tests/ -v
```

---

## 5. Step-by-Step Reproducibility

### 1. Validate Dataset Integrity
```bash
python -m data.validator --file data/BTCUSDT_1h_historical.csv --timeframe 1h
```

### 2. Generate Cryptographic Manifest
```bash
python -m data.manifest --file data/BTCUSDT_1h_historical.csv --timeframe 1h --version v1
```

### 3. Run Comparative Baseline Benchmarks
```bash
python -m training.benchmark_suite --data data/BTCUSDT_1h_historical.csv --bars 8000
```

### 4. Launch Next.js Quantitative Workstation
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the workstation:
* Non-overlapping 0px docked architecture
* Dynamic mark-to-market Unrealized PnL engine
* Active position risk monitor & TWAP order slicing ledger
* Hotkey `[E]` to collapse/expand risk dock for full-screen charting

---

## 6. 1-Click Cloud Deployment (Oracle Cloud / Ubuntu)

The repository includes an automated 1-click cloud bootstrap script:

```bash
git clone https://github.com/ajay1951/ai-trading-research-platform.git ai_crypto_bot
cd ai_crypto_bot
sudo bash scripts/setup_oracle.sh
```

**Management CLI (`nexus.sh`)**:
```bash
nexus status    # View live wallet balance, open trades, and PM2 health
nexus logs      # Stream real-time execution signals
nexus restart   # Cleanly reboot bot and web interface
nexus update    # 1-command: git pull, rebuild frontend, and restart
```

---

## 7. Known Limitations

1. **Market Impact**: Backtests model 2 bps slippage on liquid pairs ($> \$50\text{M}$ volume). Illiquid altcoins or orders $>\$500\text{k}$ require non-linear square-root market impact modeling.
2. **Regime Vulnerability**: Long-only momentum algorithms experience drawdown during multi-quarter crypto bear markets without cash defense or shorting rules.
3. **Execution Latency**: Network round-trip times to exchange matching engines (~20–120ms) can impact fill prices during major macroeconomic news spikes.

---

## 8. License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
