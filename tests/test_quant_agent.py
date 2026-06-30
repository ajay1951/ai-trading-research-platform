"""
Tests for Quantitative Analysis Agent.
"""
import unittest
import json
import numpy as np
import pandas as pd
from agents.quant_agent import QuantitativeAnalysisAgent, TechnicalIndicators, Signal, BacktestResult


class TestTechnicalIndicators(unittest.TestCase):
    def setUp(self):
        # Create sample price data
        self.prices = pd.Series([100 + i * 0.5 + np.random.randn() for i in range(100)])
        self.high = self.prices + 1
        self.low = self.prices - 1
        self.volume = pd.Series([1000] * 100)
    
    def test_sma(self):
        sma = TechnicalIndicators.sma(self.prices, 20)
        self.assertEqual(len(sma), len(self.prices))
        # First 19 values should be NaN
        self.assertTrue(pd.isna(sma.iloc[18]))
        self.assertFalse(pd.isna(sma.iloc[19]))
    
    def test_ema(self):
        ema = TechnicalIndicators.ema(self.prices, 20)
        self.assertEqual(len(ema), len(self.prices))
    
    def test_rsi_range(self):
        rsi = TechnicalIndicators.rsi(self.prices, 14)
        valid_rsi = rsi.dropna()
        self.assertTrue(all(valid_rsi >= 0))
        self.assertTrue(all(valid_rsi <= 100))
    
    def test_macd_returns_three_series(self):
        macd_line, signal_line, histogram = TechnicalIndicators.macd(self.prices)
        self.assertEqual(len(macd_line), len(self.prices))
        self.assertEqual(len(signal_line), len(self.prices))
        self.assertEqual(len(histogram), len(self.prices))
    
    def test_bollinger_bands(self):
        upper, middle, lower = TechnicalIndicators.bollinger_bands(self.prices)
        self.assertTrue(all(upper.dropna() >= middle.dropna()))
        self.assertTrue(all(lower.dropna() <= middle.dropna()))
    
    def test_atr_positive(self):
        atr = TechnicalIndicators.atr(self.high, self.low, self.prices, 14)
        valid_atr = atr.dropna()
        self.assertTrue(all(valid_atr >= 0))


class TestQuantAgent(unittest.TestCase):
    def setUp(self):
        self.agent = QuantitativeAnalysisAgent()
    
    def test_agent_initialization(self):
        self.assertIsNotNone(self.agent.tools)
        self.assertIn("indicators", self.agent.tools)
        self.assertIn("signal", self.agent.tools)
        self.assertIn("backtest", self.agent.tools)
    
    def test_execute_with_mock_data(self):
        parameters = {"symbol": "BTC/USDT"}
        context = {
            "data": {
                "market": {
                    "close_prices": [50000 + i*100 for i in range(200)],
                    "highs": [50100 + i*100 for i in range(200)],
                    "lows": [49900 + i*100 for i in range(200)],
                    "volumes": [1000] * 200
                }
            }
        }
        
        result = self.agent.execute(parameters, context)
        
        self.assertEqual(result["agent"], "quantitative_analysis")
        self.assertIn("analysis", result)
        self.assertIn("signal", result["analysis"])
        self.assertIn("indicators", result["analysis"])
    
    def test_backtest_tool(self):
        # Generate synthetic data
        close_prices = [100 + i for i in range(100)]
        ohlcv_json = json.dumps({
            "close": close_prices,
            "high": [p + 1 for p in close_prices],
            "low": [p - 1 for p in close_prices],
            "volume": [1000] * 100
        })
        
        # Generate buy-and-hold signals
        signals = json.dumps({"signals": [1 if i < 50 else -1 for i in range(100)]})
        
        backtest_tool = self.agent.tools["backtest"]
        result_raw = backtest_tool._run(ohlcv_json, signals, 10000)
        result = json.loads(result_raw)
        
        self.assertIn("total_return", result)
        self.assertIn("sharpe_ratio", result)
        self.assertIn("max_drawdown", result)


if __name__ == "__main__":
    unittest.main()
