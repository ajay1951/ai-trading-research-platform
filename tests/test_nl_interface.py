"""
Tests for Natural Language Interface.
"""
import unittest
from core.nl_interface import NaturalLanguageInterface, ParsedQuery


class TestNaturalLanguageInterface(unittest.TestCase):
    def setUp(self):
        self.nli = NaturalLanguageInterface()
    
    def test_parse_query_with_ticker(self):
        query = "Analyze BTC/USDT for trading opportunities"
        parsed = self.nli.parse_query(query)
        
        self.assertIn("BTC/USDT", parsed.entities.get("tickers", []))
        self.assertEqual(parsed.intent, "analyze")
    
    def test_parse_query_with_timeframe(self):
        query = "Show me 4h chart for ETH"
        parsed = self.nli.parse_query(query)
        self.assertEqual(parsed.timeframe, "4h")
    
    def test_parse_query_with_metrics(self):
        query = "What's the RSI and MACD for BTC?"
        parsed = self.nli.parse_query(query)
        self.assertIn("rsi", parsed.entities.get("metrics", []))
        self.assertIn("macd", parsed.entities.get("metrics", []))
    
    def test_parse_trade_intent(self):
        query = "Should I buy ETH right now?"
        parsed = self.nli.parse_query(query)
        self.assertEqual(parsed.intent, "trade")
    
    def test_parse_risk_intent(self):
        query = "Calculate VaR for my portfolio"
        parsed = self.nli.parse_query(query)
        self.assertEqual(parsed.intent, "risk")
    
    def test_generate_response(self):
        results = {
            "success": True,
            "results": {
                "data": {"status": "Data fetched successfully"},
                "quant": {"signal": "BUY", "strength": 0.8}
            }
        }
        parsed = ParsedQuery(intent="analyze", entities={"symbol": "BTC/USDT"}, raw_query="Analyze BTC")
        
        response = self.nli.generate_response(results, parsed)
        
        self.assertIn("ANALYSIS REPORT", response)
        self.assertIn("BTC/USDT", response)
        self.assertIn("BUY", response)


if __name__ == "__main__":
    unittest.main()
