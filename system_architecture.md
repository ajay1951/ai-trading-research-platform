# Multi-Agent Institutional Crypto Architecture
**Complete System Documentation & Technical Review**

This document outlines exactly how the AI Crypto Bot works, the technologies used, and how the various agents communicate to execute High-Frequency, Multi-Timeframe trades.

---

## 🛠️ The Technology Stack

- **Brain:** `PyTorch` (Configured with Nvidia CUDA 12.1 for massive GPU parallel processing).
- **Data Manipulation:** `Pandas` and `NumPy` for heavy rolling matrix calculations.
- **Sentiment Scraping:** `BeautifulSoup4` and the `Wayback Machine API` for pulling 7 years of historical news data.
- **Future Live Execution:** `CCXT` (CryptoCurrency eXchange Trading Library) to connect directly to Binance or Bybit.

---

## 🧠 The Multi-Agent System

This is not a single script making random guesses. It is a "Committee of Experts," where 4 distinct Agents collaborate to make a single trading decision.

### 1. The Quant Agent (`agents/quant_agent.py`)
- **Role:** The Mathematician.
- **How it works:** It does not look at the price of Bitcoin; it looks at the *math behind the price*. It calculates the **Z-Score** across 5 different timeframes to mathematically prove if an asset is overbought or oversold compared to its historical mean.

### 2. The Sentiment Agent (`agents/sentiment_agent.py`)
- **Role:** The Global Reader.
- **How it works:** It takes the parsed Google News headlines from our historical database, looks for keywords (e.g., "Ban", "ETF", "Hack", "Moon"), and assigns a Fear/Greed score from `-1.0` (Extreme Fear) to `1.0` (Extreme Greed).

### 3. The Risk Agent (`agents/risk_agent.py`)
- **Role:** The Capital Guardian.
- **How it works:** It uses the **Average True Range (ATR)** to calculate real-time market volatility. If the Meta-Agent says "Buy BTC," the Risk Agent steps in and says, *"Wait, volatility is too high right now. Throttle the position size down to 5% to protect our capital."*

### 4. The Meta-Agent (`agents/meta_agent.py`)
- **Role:** The Institutional Boss (Double Deep Q-Network).
- **How it works:** This is the PyTorch Neural Network. It ingests an **8-Dimensional X-Ray Tensor**, taking the advice from the Quant and Sentiment agents, while also looking directly at the 1-month macro trends and 1-minute flash crash data. It uses Bellman Equations to calculate the highest possible future reward (maximizing the Sharpe Ratio).

---

## ⚙️ How The Engine Works (The Pipeline)

When you run `python training\train_dqn.py`, the system executes the following pipeline:

### Step 1: Multi-Timeframe Data Merge (`quant_features.py`)
The system simultaneously loads the `1m`, `1h`, `1d`, `1w`, and `1mo` historical CSV files. Because processing 7 years of 1-minute data would crash a computer, it uses an advanced Pandas logic to calculate the *High-Frequency Volatility* of the 1-minute data and mathematically stitches it directly onto the 1-day execution timeframe. 

### Step 2: The Matrix Simulator (`trading_env.py`)
The stitched data is passed to the Custom Trading Environment. This simulator mimics a real crypto exchange. It tracks the bot's fake USD balance, applies trading fees (slippage), and calculates the bot's ongoing portfolio value.

### Step 3: PyTorch GPU Execution (`train_dqn.py`)
The simulator steps through the 7 years of data day-by-day. At every single step:
1. It passes the current state to the Meta-Agent.
2. The Meta-Agent makes a decision (-1.0 to 1.0).
3. The Risk Agent throttles the decision size based on ATR.
4. The Simulator executes the trade and returns a Reward.
5. The PyTorch Neural Network runs backpropagation on your RTX 2050 GPU to mathematically refine its weights.

This process is repeated **1,000 times (Epochs)** until the bot achieves absolute perfection in maximizing the Sharpe Ratio.
