import pytest
import asyncio
import time
from core.orchestrator import MasterCoordinator, AgentCapability

class MockDataAgent:
    def __init__(self, memory):
        self.memory = memory

    async def execute(self, params, context):
        # Simulate Fast Lane processing (e.g. 0.01s)
        await asyncio.sleep(0.01)
        return {"data": {"market": {"price": 50000}}}

class MockQuantAgent:
    async def execute(self, params, context):
        await asyncio.sleep(0.01)
        return {"signal": "BUY"}

class MockRiskAgent:
    async def execute(self, params, context):
        await asyncio.sleep(0.01)
        return {"risk_assessment": {"var": {"var": 0.05}}}

class MockResearchAgentSlow:
    async def execute(self, params, context):
        # Simulate Slow Lane LLM hang (exactly 5s as requested)
        await asyncio.sleep(5.0)
        return {"research": "LLM output"}

class MockSupervisorAgent:
    async def execute(self, params, context):
        await asyncio.sleep(0.01)
        return {"final_signal": "BUY"}

@pytest.mark.asyncio
async def test_fast_lane_bypasses_slow_lane():
    coordinator = MasterCoordinator()
    memory = coordinator.memory
    memory.clear()  # Clear synchronous JSON dump bottleneck
    
    # Register Fast Lane (Math/Data/Risk)
    coordinator.register_agent("data", MockDataAgent(memory), AgentCapability("data", "", []))
    coordinator.register_agent("quant", MockQuantAgent(), AgentCapability("quant", "", ["data"]))
    coordinator.register_agent("risk", MockRiskAgent(), AgentCapability("risk", "", ["quant"]))
    
    # Register Slow Lane (LLMs)
    coordinator.register_agent("research", MockResearchAgentSlow(), AgentCapability("research", "", ["data"]))
    coordinator.register_agent("supervisor", MockSupervisorAgent(), AgentCapability("supervisor", "", ["research", "risk"]))
    
    print("\n[TEST] Submitting WebSocket payload to dual-lane Orchestrator...")
    start_time = time.time()
    
    # Route query (this will execute Fast Lane synchronously and Slow Lane in background)
    result = await coordinator.route_query("fetch market data calculate technical indicators evaluate risk fundamental research analyze")
    
    fast_lane_elapsed = time.time() - start_time
    
    # Assert that the fast lane elapsed is strictly under 0.1s
    print(f"[METRIC] Fast Lane Execution Time: {fast_lane_elapsed:.4f}s")
    assert fast_lane_elapsed < 0.1, f"Fast Lane was BLOCKED! Time: {fast_lane_elapsed}s"
    
    # Verify that the fast lane results are instantly returned
    assert "data" in result["results"]
    assert "quant" in result["results"]
    assert "risk" in result["results"]
    
    # Verify that the slow lane results are NOT in the immediate return
    assert "research" not in result["results"]
    assert "supervisor" not in result["results"]
    
    print("[TEST] Fast Lane validated. Now awaiting background Slow Lane tasks...")
    # Await exactly 5.1s to allow the background asyncio task to complete
    await asyncio.sleep(5.2)
    
    slow_lane_elapsed = time.time() - start_time
    print(f"[METRIC] Slow Lane Total Execution Time: {slow_lane_elapsed:.4f}s")
    
    # Validate the Slow Lane successfully piped its data to SharedMemory upon completion
    final_query_keys = [k for k in memory.get_all_keys() if k.startswith("final:query:") and not k.endswith("_fast")]
    assert len(final_query_keys) > 0, "Slow lane background task failed to complete or write to memory!"
    
    final_output = memory.get(final_query_keys[0])
    assert "research" in final_output["results"]
    assert "supervisor" in final_output["results"]
    print("[TEST] Concurrency architecture mathematically validated!")
