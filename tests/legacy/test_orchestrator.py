"""
Tests for Master Orchestrator.
"""
import unittest
import asyncio
from core.orchestrator import MasterCoordinator, AgentCapability


class MockAgent:
    """Mock agent for testing."""
    def __init__(self, name: str, delay: float = 0):
        self.name = name
        self.delay = delay
        self.executed = False
    
    def execute(self, parameters, context):
        self.executed = True
        if self.delay > 0:
            import time
            time.sleep(self.delay)
        return {
            "agent": self.name,
            "result": f"Executed {self.name}",
            "timestamp": "2024-01-01T00:00:00"
        }
    
    def get_capability(self):
        return {
            "name": self.name,
            "description": f"Mock {self.name}",
            "supported_operations": ["test"],
            "dependencies": []
        }


class TestMasterCoordinator(unittest.TestCase):
    def setUp(self):
        self.coordinator = MasterCoordinator()
    
    def test_register_agent(self):
        agent = MockAgent("test_agent")
        cap = AgentCapability(
            name="test",
            description="Test agent",
            supported_operations=["test"],
            dependencies=[]
        )
        self.coordinator.register_agent("test", agent, cap)
        self.assertIn("test", self.coordinator._agents)
    
    def test_unregister_agent(self):
        agent = MockAgent("test_agent")
        cap = AgentCapability("test", "Test", ["test"])
        self.coordinator.register_agent("test", agent, cap)
        self.coordinator.unregister_agent("test")
        self.assertNotIn("test", self.coordinator._agents)
    
    def test_detect_intent(self):
        # Test different query types
        intent = self.coordinator._detect_intent("Buy BTC now")
        self.assertEqual(intent.action, "trade")
        self.assertIn("execution", intent.target_agents)
        
        intent2 = self.coordinator._detect_intent("Analyze BTC technical indicators")
        self.assertEqual(intent2.action, "analyze")
        self.assertIn("quant", intent2.target_agents)
        
        intent3 = self.coordinator._detect_intent("What's the risk?")
        self.assertEqual(intent3.action, "assess_risk")
    
    def test_resolve_dependencies(self):
        # Register agents with dependencies
        agent1 = MockAgent("data")
        agent2 = MockAgent("quant")
        agent3 = MockAgent("risk")
        
        cap1 = AgentCapability("data", "Data", ["fetch"], [])
        cap2 = AgentCapability("quant", "Quant", ["analyze"], ["data"])
        cap3 = AgentCapability("risk", "Risk", ["assess"], ["quant", "data"])
        
        self.coordinator.register_agent("data", agent1, cap1)
        self.coordinator.register_agent("quant", agent2, cap2)
        self.coordinator.register_agent("risk", agent3, cap3)
        
        order = self.coordinator._resolve_dependencies(["risk"])
        # data should come before risk
        self.assertLess(order.index("data"), order.index("risk"))
        # quant should come before risk
        self.assertLess(order.index("quant"), order.index("risk"))
    
    async def test_route_query(self):
        agent = MockAgent("test")
        cap = AgentCapability("test", "Test", ["test"], [])
        self.coordinator.register_agent("test", agent, cap)
        
        result = await self.coordinator.route_query("Test query")
        
        self.assertIn("intent", result)
        self.assertIn("results", result)
        self.assertIn("test", result["results"])
        self.assertTrue(agent.executed)


class TestCoordinatorIntegration(unittest.TestCase):
    def test_agent_status_tracking(self):
        coordinator = MasterCoordinator()
        agent = MockAgent("test")
        cap = AgentCapability("test", "Test", ["test"], [])
        coordinator.register_agent("test", agent, cap)
        
        # Initially idle
        status = coordinator.get_agent_status()
        self.assertEqual(status["test"], "idle")
        
        # After execution, status returns to idle


if __name__ == "__main__":
    # Run async tests
    async def run_async_tests():
        coordinator = MasterCoordinator()
        agent = MockAgent("test")
        cap = AgentCapability("test", "Test", ["test"], [])
        coordinator.register_agent("test", agent, cap)
        result = await coordinator.route_query("Test")
        print("Async test result:", result)
    
    unittest.main()
