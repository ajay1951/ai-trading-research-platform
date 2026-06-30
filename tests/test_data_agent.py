"""
Tests for Real-Time Data Retrieval Agent.
"""
import unittest
import json
from unittest.mock import patch, MagicMock
from agents.data_agent import RealTimeDataAgent, FetchMarketDataTool, FetchNewsTool, FetchSECFilingsTool


class TestFetchMarketDataTool(unittest.TestCase):
    @patch('agents.data_agent.WebSocketMarketData')
    def test_fetch_market_data_success(self, mock_ws):
        # Mock the fetch_ohlcv method
        from datetime import datetime
        mock_instance = mock_ws.return_value
        mock_instance.fetch_ohlcv.return_value = [
            type('MarketData', (), {
                'symbol': 'BTC/USDT',
                'timestamp': datetime.now(),
                'open': 50000,
                'high': 51000,
                'low': 49000,
                'close': 50500,
                'volume': 1000,
                'exchange': 'binance',
                'timeframe': '1h'
            })()
        ]
        
        tool = FetchMarketDataTool()
        result_raw = tool._run("BTC/USDT", "1h", 10)
        result = json.loads(result_raw)
        
        self.assertEqual(result["symbol"], "BTC/USDT")
        self.assertEqual(result["last_price"], 50500)
        self.assertEqual(result["volume"], 1000)


class TestFetchNewsTool(unittest.TestCase):
    @patch('agents.data_agent.NewsAPIClient')
    def test_fetch_news_success(self, mock_news):
        mock_instance = mock_news.return_value
        mock_instance.fetch_crypto_news.return_value = [
            {"title": "BTC news", "url": "http://example.com", "source": "CoinDesk"},
            {"title": "Crypto update", "url": "http://example2.com", "source": "CoinTelegraph"}
        ]
        mock_instance.fetch_fear_greed_index.return_value = {"value": 65, "classification": "Greed"}
        
        tool = FetchNewsTool()
        result_raw = tool._run("BTC", 5)
        result = json.loads(result_raw)
        
        self.assertEqual(len(result["news"]), 2)
        self.assertEqual(result["fear_greed_index"], 65)


class TestFetchSECFilingsTool(unittest.TestCase):
    @patch('agents.data_agent.SECAPIClient')
    def test_fetch_sec_filings(self, mock_sec):
        mock_instance = mock_sec.return_value
        mock_instance.get_company_cik.return_value = "0001318605"
        mock_instance.fetch_filings.return_value = [
            {
                "type": "10-K",
                "date": "2024-01-15",
                "accession": "0001318605-24-000005"
            }
        ]
        
        tool = FetchSECFilingsTool()
        result_raw = tool._run("TSLA", "10-K", 3)
        result = json.loads(result_raw)
        
        self.assertEqual(result["ticker"], "TSLA")
        self.assertEqual(result["cik"], "0001318605")
        self.assertEqual(len(result["filings"]), 1)


class TestRealTimeDataAgent(unittest.TestCase):
    def setUp(self):
        self.agent = RealTimeDataAgent()
    
    def test_agent_execute(self):
        # Mock tools
        self.agent.tools["market_data"]._run = MagicMock(return_value='{"last_price": 50000}')
        self.agent.tools["news"]._run = MagicMock(return_value='{"news": []}')
        
        parameters = {"symbol": "BTC/USDT"}
        context = {}
        
        result = self.agent.execute(parameters, context)
        
        self.assertEqual(result["agent"], "data_retrieval")
        self.assertIn("data", result)
        self.assertIn("market", result["data"])
        self.agent.tools["market_data"]._run.assert_called_once()
    
    def test_capability(self):
        cap = self.agent.get_capability()
        self.assertEqual(cap["name"], "data_retrieval")
        self.assertIn("fetch_market_data", cap["supported_operations"])


if __name__ == "__main__":
    unittest.main()
