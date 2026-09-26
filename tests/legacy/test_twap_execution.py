import pytest
import asyncio
from unittest.mock import patch
from tools.execution_tools import WebSocketExecutionStream
from core.memory import SharedMemory

@pytest.mark.asyncio
async def test_twap_execution():
    # Setup test memory
    memory = SharedMemory()
    memory.clear()
    
    execution_stream = WebSocketExecutionStream(memory=memory)
    
    # Payload for a $5,000 order ($50,000 BTC * 0.1)
    payload = {
        "action": "BUY",
        "symbol": "BTC/USDT",
        "amount": 0.1,
        "price": 50000.0,
        "mode": "paper",
        "stop_loss": 40000.0,
        "take_profit": 80000.0
    }
    
    # We will subscribe to trade_executed to catch the final blended TWAP event
    received_payloads = []
    
    def on_trade(msg):
        if msg["sender"] == "execution_stream_twap":
            received_payloads.append(msg["data"])
            
    memory.subscribe("trade_executed", on_trade)
    
    original_sleep = asyncio.sleep
    
    async def mock_sleep(delay):
        # We still need to yield to the event loop so tasks can run
        await original_sleep(0)
        
    # Mock asyncio.sleep only in execution_tools so the 5-10 minute loop executes instantly
    with patch("tools.execution_tools.asyncio.sleep", new=mock_sleep):
        # We process the order. It should spawn a task for _execute_twap_block
        await execution_stream._process_order(payload)
        
        # Wait for the background task to finish
        # Since sleep(0) is used, it should be done in ~50 iterations
        for _ in range(100):
            await asyncio.sleep(0.01)
            if len(received_payloads) > 0:
                break
        
    # Verify the results
    assert len(received_payloads) == 1, "Expected exactly 1 final TWAP payload"
    
    final_payload = received_payloads[0]
    
    # Verify it sliced into 50 chunks ($5000 / $100)
    assert final_payload["chunks"] == 50, f"Expected 50 chunks, got {final_payload['chunks']}"
    assert final_payload["amount"] == pytest.approx(0.1), "Total amount executed does not match requested amount"
    assert final_payload["price"] == pytest.approx(50000.0), "Blended price is incorrect"
    assert final_payload["status"] == "TWAP_COMPLETED"
    
    # Ensure guardrails were respected for the overall order but chunks processed
    assert final_payload["action"] == "BUY"
    assert final_payload["symbol"] == "BTC/USDT"
