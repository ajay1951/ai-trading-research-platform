import pytest
import asyncio
import time
from core.orchestrator import MasterCoordinator
from tools.execution_tools import execution_stream

@pytest.mark.asyncio
async def test_emergency_circuit_breaker():
    coordinator = MasterCoordinator()
    memory = coordinator.memory
    memory.clear()

    # Enable dummy mode and reset execution stream
    memory.store("trading_mode", "paper")
    
    # We will mock the execution_stream order_queue
    execution_stream.order_queue = asyncio.Queue()
    
    # Start the monitor manually
    monitor_task = asyncio.create_task(coordinator.emergency_monitor.start())
    
    # Wait for monitor to start
    await asyncio.sleep(0.1)

    # 1. Set initial equity
    initial_equity = 10000.0
    memory.store("account_equity", initial_equity)
    
    # Wait for the monitor to pick it up (sleep > 5s because loop is every 5s)
    # Actually, to speed up testing, we can directly call the logic or just shorten sleep in monitor.
    # Instead of waiting 5 seconds, let's just trigger it directly by patching sleep or manually running one iteration.
    
    # For robust testing without waiting 5 seconds, we can just call the monitor logic directly if we inject values
    # Or just wait... we'll just wait for one tick
    # Wait, we can just inject into equity_history directly to avoid sleep
    coordinator.emergency_monitor.equity_history.append((time.time() - 10, 10000.0))
    
    # 2. Simulate 6% drop
    memory.store("account_equity", 9400.0) # 6% drop
    
    # Let the loop process it
    await asyncio.sleep(5.5)
    
    # Check if halted
    assert coordinator.is_halted is True, "System did not halt after 6% drawdown!"
    assert coordinator.emergency_monitor._is_running is False, "Monitor did not stop after halt!"
    
    # Check if execution stream received the LIQUIDATE_ALL payload
    assert not execution_stream.order_queue.empty(), "Execution stream did not receive liquidation payload!"
    
    payload = await execution_stream.order_queue.get()
    assert payload["action"] == "LIQUIDATE_ALL", f"Expected LIQUIDATE_ALL, got {payload['action']}"
    assert payload["mode"] == "paper", "Expected paper mode for testing."
    
    # Clean up
    monitor_task.cancel()
