# 🌌 Universal AI Quantitative Terminal

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PyTorch](https://img.shields.io/badge/PyTorch-Deep%20Learning-EE4C2C.svg)
![TradingView](https://img.shields.io/badge/UI-TradingView%20Charts-131722.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

An institutional-grade, multi-asset algorithmic trading engine powered by an **18-Dimensional Deep Q-Network (DQN)**. Designed to operate as a fully autonomous quantitative hedge fund, this system ingests live market data, evaluates mathematical risk, executes bi-directional trades (Long/Short), and tracks portfolio performance through a premium glassmorphism web dashboard.

---

## 🧠 Core Architecture

The system is built on a highly modular, decoupled architecture separating the machine learning brain from the execution engine and the user interface.

### 1. The Universal Meta-Agent
Unlike traditional bots that rely on hardcoded indicators (RSI, MACD), this engine utilizes a Deep Reinforcement Learning Agent (`agents/meta_agent.py`). 
- **18-Dimensional State Space:** Ingests normalized Z-scores, rolling volatility metrics, volume spikes, and macro structural trends.
- **Multi-Asset Generalization:** Trained via walk-forward validation on 8 years of historical data across 5 distinct assets (`BTC`, `ETH`, `BNB`, `SOL`, `XRP`). The brain learns universal market mechanics rather than over-fitting to a single coin.

### 2. Live Execution Engine
The `live_trader.py` script acts as the automated execution layer.
- **Bi-Directional Trading:** Capable of borrowing and short-selling assets to profit during macro market crashes.
- **Risk Desk (`risk_agent.py`):** Dynamically scales position sizes based on neural network confidence thresholds.
- **Swing Trade Logic:** Operates on the `15m` timeframe with strict, mathematically enforced Take-Profit (+2%) and Stop-Loss (-1%) constraints to mitigate exchange fee bleed and whipsaw volatility.

### 3. Glassmorphism Hedge Fund Terminal
A modern, real-time command center built with Flask and Vanilla JS.
- **Live TradingView Integration:** Automatically plots real-time price action and overlays glowing AI execution markers natively on the candlesticks.
- **Virtual Portfolio Tracking:** Calculates live Realized PNL, accounting for standard 0.1% exchange fees.

---

## 🚀 Quick Start Guide

### 1. Installation
Clone the repository and install the necessary dependencies:
```bash
git clone https://github.com/your-username/universal-ai-fund.git
cd universal-ai-fund
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Launch the Web Dashboard
Start the Flask server to bring the terminal online:
```bash
python dashboard/app.py
```
*Navigate to `http://localhost:5000` in your browser.*

### 3. Ignite the AI Engine
Open a second terminal window and start the autonomous trading loop:
```bash
python scripts/live_trader.py
```
*The AI will load its pre-trained `.pth` weights, initialize a virtual $10,000 bank account, and begin actively scanning all 5 coins every 15 seconds.*

---

## 📂 Project Structure

```text
universal-ai-fund/
│
├── agents/                 # AI Logic and Risk Management
│   ├── meta_agent.py       # Deep Q-Network Brain
│   └── risk_agent.py       # Position sizing and capital allocation
│
├── backtesting/            # Historical validation engines
│   └── quant_features.py   # State vector normalization logic
│
├── dashboard/              # Flask Web Server
│   ├── app.py              # Backend API and routing
│   └── templates/
│       └── index.html      # Premium TradingView UI
│
├── data/                   # Local Datastores
│   ├── live_trades.csv     # Execution logs
│   └── portfolio.json      # Virtual account balances
│
├── scripts/                # Utility and Execution Scripts
│   ├── sync_market_data.py # Historical data scraper via CCXT
│   └── live_trader.py      # The 24/7 master execution loop
│
└── training/               # Model Training Pipelines
    └── train_dqn.py        # Multi-asset walk-forward trainer
```

---

## ⚠️ Disclaimer
*This software is for educational and research purposes only. Do not risk money which you are afraid to lose. USE THE SOFTWARE AT YOUR OWN RISK. THE AUTHORS AND ALL AFFILIATES ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS.*
