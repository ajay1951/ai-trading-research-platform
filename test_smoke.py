#!/usr/bin/env python
"""
Smoke test - Verify all imports and basic agent functionality.
"""
import sys
import traceback


def test_imports():
    """Test that all modules import without errors."""
    print("="*60)
    print("SMOKE TEST: Import Check")
    print("="*60)
    
    modules = [
        ('core.memory', 'SharedMemory'),
        ('core.orchestrator', 'MasterCoordinator'),
        ('core.nl_interface', 'NaturalLanguageInterface'),
        ('core.storage', 'DataManager'),
        ('agents.data_agent', 'RealTimeDataAgent'),
        ('agents.quant_agent', 'QuantitativeAnalysisAgent'),
        ('agents.research_agent', 'FundamentalResearchAgent'),
        ('agents.risk_agent', 'RiskManagementAgent'),
        ('models.technical_indicators', 'TechnicalIndicators'),
        ('models.risk_models', 'ValueAtRisk'),
    ]
    
    errors = []
    for module_name, class_name in modules:
        try:
            module = __import__(module_name, fromlist=[class_name])
            cls = getattr(module, class_name)
            print(f"  [OK] {module_name}.{class_name}")
        except Exception as e:
            print(f"  [FAIL] {module_name}.{class_name}: {e}")
            errors.append((module_name, str(e)))
    
    return len(errors) == 0


def test_agent_instantiation():
    """Test that agents can be instantiated."""
    print("\n" + "="*60)
    print("SMOKE TEST: Agent Instantiation")
    print("="*60)
    
    from core.memory import SharedMemory
    from agents.data_agent import RealTimeDataAgent
    from agents.quant_agent import QuantitativeAnalysisAgent
    from agents.research_agent import FundamentalResearchAgent
    from agents.risk_agent import RiskManagementAgent
    
    memory = SharedMemory()
    
    agents = [
        ('Data Agent', RealTimeDataAgent),
        ('Quant Agent', QuantitativeAnalysisAgent),
        ('Research Agent', FundamentalResearchAgent),
        ('Risk Agent', RiskManagementAgent),
    ]
    
    errors = []
    for name, agent_class in agents:
        try:
            agent = agent_class(memory)
            print(f"  [OK] {name} instantiated")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            errors.append(name)
    
    return len(errors) == 0


def test_basic_functionality():
    """Test basic agent functionality."""
    print("\n" + "="*60)
    print("SMOKE TEST: Basic Functionality")
    print("="*60)
    
    from agents.quant_agent import TechnicalIndicators
    import pandas as pd
    import numpy as np
    
    # Test technical indicator calculations
    prices = pd.Series([100 + i + np.random.randn() for i in range(100)])
    
    try:
        sma = TechnicalIndicators.sma(prices, 20)
        assert len(sma) == 100
        print("  [OK] SMA calculation")
        
        rsi = TechnicalIndicators.rsi(prices, 14)
        valid_rsi = rsi.dropna()
        assert all(valid_rsi >= 0) and all(valid_rsi <= 100)
        print("  [OK] RSI calculation")
        
        macd_line, signal, hist = TechnicalIndicators.macd(prices)
        assert len(macd_line) == 100
        print("  [OK] MACD calculation")
        
    except Exception as e:
        print(f"  [FAIL] Technical indicators: {e}")
        return False
    
    # Test risk models
    try:
        from models.risk_models import ValueAtRisk, PortfolioAnalyzer
        
        returns = np.random.normal(0.001, 0.02, 365)
        var_calc = ValueAtRisk(returns, 100000)
        var = var_calc.calculate(method="historical")
        assert var.var_95 > 0
        print("  [OK] VaR calculation")
        
        portfolio = {"BTC": 50000, "ETH": 30000}
        analyzer = PortfolioAnalyzer()
        hhi = analyzer.calculate_concentration(portfolio)
        assert 0 <= hhi <= 10000
        print("  [OK] Portfolio concentration")
        
    except Exception as e:
        print(f"  [FAIL] Risk models: {e}")
        return False
    
    return True


def test_nl_interface():
    """Test natural language parsing."""
    print("\n" + "="*60)
    print("SMOKE TEST: Natural Language Interface")
    print("="*60)
    
    try:
        from core.nl_interface import nl_interface
        
        queries = [
            ("Analyze BTC/USDT", "analyze", ["BTC/USDT"]),
            ("Buy ETH now", "trade", ["ETH"]),
            ("Calculate VaR", "risk", []),
        ]
        
        for query, expected_intent, expected_entities in queries:
            parsed = nl_interface.parse_query(query)
            assert parsed.intent == expected_intent, f"Expected {expected_intent}, got {parsed.intent}"
            if expected_entities:
                for entity in expected_entities:
                    assert entity in str(parsed.entities), f"Expected entity {entity}"
            print(f"  [OK] '{query}' -> {parsed.intent}")
        
        return True
    except Exception as e:
        print(f"  [FAIL] NL Interface: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_orchestrator():
    """Test master coordinator routing."""
    print("\n" + "="*60)
    print("SMOKE TEST: Master Coordinator")
    print("="*60)
    
    try:
        from core.orchestrator import coordinator, AgentCapability
        from core.memory import SharedMemory
        
        memory = SharedMemory()
        
        # Create mock agent
        class MockAgent:
            def execute(self, params, context):
                return {"agent": "test", "status": "ok"}
            
            def get_capability(self):
                return {
                    "name": "test",
                    "description": "Test agent",
                    "supported_operations": ["test"],
                    "dependencies": []
                }
        
        agent = MockAgent()
        cap = AgentCapability("test", "Test", ["test"], [])
        coordinator.register_agent("test", agent, cap)
        
        print("  [OK] Agent registered")
        
        # Test intent detection
        intent = coordinator._detect_intent("Analyze BTC")
        assert "quant" in intent.target_agents or "data" in intent.target_agents
        print("  [OK] Intent detection works")
        
        return True
    except Exception as e:
        print(f"  [FAIL] Orchestrator: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all smoke tests."""
    print("\n" + "="*60)
    print("MULTI-AGENT FINANCIAL AI - SMOKE TEST")
    print("="*60 + "\n")
    
    results = []
    
    # Test 1: Imports
    results.append(("Imports", test_imports()))
    
    # Test 2: Agent instantiation
    results.append(("Agent Instantiation", test_agent_instantiation()))
    
    # Test 3: Basic functionality (indicators, risk models)
    results.append(("Basic Functionality", test_basic_functionality()))
    
    # Test 4: NL Interface
    results.append(("NL Interface", test_nl_interface()))
    
    # Test 5: Orchestrator
    results.append(("Orchestrator", test_orchestrator()))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All smoke tests passed! System is ready.")
        return 0
    else:
        print("\n[WARNING] Some tests failed. Check logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
