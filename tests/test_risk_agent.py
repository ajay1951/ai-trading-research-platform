"""
Tests for Risk Management Agent.
"""
import unittest
import json
import numpy as np
import pandas as pd
from agents.risk_agent import RiskManagementAgent, CalculateVaRTool, StressTestTool, PortfolioAnalyzer


class TestVaRTool(unittest.TestCase):
    def setUp(self):
        self.tool = CalculateVaRTool()
        # Generate synthetic returns
        np.random.seed(42)
        self.returns = np.random.normal(0.001, 0.02, 365).tolist()
    
    def test_var_calculation(self):
        result_raw = self.tool._run(json.dumps(self.returns), confidence=0.95, method="historical")
        result = json.loads(result_raw)
        
        self.assertIn("var", result)
        self.assertIn("cvar", result)
        self.assertIn("method", result)
        self.assertGreater(result["var"], 0)  # VaR should be positive (as percentage)
    
    def test_var_parametric(self):
        result_raw = self.tool._run(json.dumps(self.returns), confidence=0.95, method="parametric")
        result = json.loads(result_raw)
        self.assertEqual(result["method"], "parametric")
    
    def test_var_insufficient_data(self):
        result_raw = self.tool._run(json.dumps([0.01, -0.02]), confidence=0.95)
        result = json.loads(result_raw)
        self.assertIn("error", result)


class TestStressTestTool(unittest.TestCase):
    def setUp(self):
        self.tool = StressTestTool()
    
    def test_standard_scenarios(self):
        result_raw = self.tool._run(100000, None, ["2008_crisis", "2020_covid"])
        result = json.loads(result_raw)
        
        self.assertIn("scenarios_tested", result)
        self.assertIn("results", result)
        self.assertEqual(result["scenarios_tested"], 2)
    
    def test_custom_scenario(self):
        custom = [{"name": "test", "description": "test scenario", "shock": -0.10}]
        result_raw = self.tool._run(100000, None, custom)
        result = json.loads(result_raw)
        
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["impact_pct"], -10.0)
    
    def test_severity_classification(self):
        self.assertEqual(self.tool._classify_severity(-50), "severe")
        self.assertEqual(self.tool._classify_severity(-25), "moderate")
        self.assertEqual(self.tool._classify_severity(-10), "mild")


class TestPortfolioAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = PortfolioAnalyzer()
    
    def test_concentration_hhi(self):
        # Equal weights -> low concentration
        equal_weights = {"BTC": 0.25, "ETH": 0.25, "SOL": 0.25, "AVAX": 0.25}
        hhi = self.analyzer.calculate_concentration(equal_weights)
        self.assertLess(hhi, 3000)  # Should be 2500 for 4 assets equally weighted
        
        # Single asset -> max concentration
        single = {"BTC": 1.0}
        hhi_single = self.analyzer.calculate_concentration(single)
        self.assertEqual(hhi_single, 10000)
    
    def test_max_position(self):
        portfolio = {"BTC": 0.5, "ETH": 0.3, "USDT": 0.2}
        asset, weight = self.analyzer.max_position_size(portfolio)
        self.assertEqual(asset, "BTC")
        self.assertEqual(weight, 0.5)
    
    def test_sector_exposure(self):
        portfolio = {"BTC": 0.4, "ETH": 0.4, "AAPL": 0.2}
        sector_map = {"BTC": "crypto", "ETH": "crypto", "AAPL": "tech"}
        exposure = self.analyzer.sector_exposure(portfolio, sector_map)
        self.assertEqual(exposure["crypto"], 0.8)
        self.assertEqual(exposure["tech"], 0.2)


class TestRiskAgent(unittest.TestCase):
    def setUp(self):
        self.agent = RiskManagementAgent()
    
    def test_agent_initialization(self):
        self.assertIsNotNone(self.agent.tools)
        self.assertIn("var", self.agent.tools)
        self.assertIn("stress", self.agent.tools)
        self.assertIn("sl_tp", self.agent.tools)
    
    def test_execute_with_context(self):
        parameters = {"symbol": "BTC/USDT", "price": 50000}
        context = {
            "quant": {
                "analysis": {
                    "indicators": {"atr": 1500}
                }
            }
        }
        
        result = self.agent.execute(parameters, context)
        
        self.assertEqual(result["agent"], "risk_management")
        self.assertIn("risk_assessment", result)
        self.assertIn("recommendation", result)
    
    def test_risk_level_assessment(self):
        # High risk scenario
        var_data = {"var": 8.0}
        stress_data = {"worst_case": {"impact_pct": -45}}
        sl_tp = {"rr_ratio": 0.8}
        
        level = self.agent._assess_risk_level(var_data, stress_data, sl_tp)
        self.assertEqual(level, "HIGH")
        
        # Low risk scenario
        var_data2 = {"var": 2.0}
        stress_data2 = {"worst_case": {"impact_pct": -10}}
        sl_tp2 = {"rr_ratio": 2.0}
        
        level2 = self.agent._assess_risk_level(var_data2, stress_data2, sl_tp2)
        self.assertEqual(level2, "LOW")
    
    def test_calculate_var(self):
        portfolio = {"BTC": 50000, "ETH": 30000}
        var_result = self.agent.calculate_var(portfolio, 0.95)
        
        self.assertIsInstance(var_result, type(self.agent.calculate_var.__annotations__['return']))
        self.assertGreater(var_result.var_95, 0)
        self.assertEqual(var_result.portfolio_value, 80000)
    
    def test_stress_test(self):
        scenarios = [
            {"name": "test1", "shock": -0.20},
            {"name": "test2", "shock": -0.40}
        ]
        results = self.agent.stress_test(scenarios, 100000)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].portfolio_impact_value, -20000)


if __name__ == "__main__":
    unittest.main()
