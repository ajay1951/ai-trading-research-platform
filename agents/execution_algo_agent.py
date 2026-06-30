from typing import Dict, Any, List
from core.memory import SharedMemory
import math
import time

class ExecutionAlgoAgent:
    """
    Algorithmic Execution Agent.
    Slices large "Parent Orders" into smaller "Child Orders" using TWAP.
    """
    def __init__(self, memory: SharedMemory):
        self.memory = memory
        self.max_child_order_usd = 50000.0 # Maximum size of a single slice

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Simulates TWAP algorithmic slicing.
        """
        # Read the approved order from execution agent
        exec_details = context.get("execution", {}).get("trade_details", {})
        if not exec_details:
             return {"status": "NO_ORDER", "reason": "No approved order to slice."}
             
        action = exec_details.get("action")
        if action not in ["BUY", "SELL"]:
            return {"status": "NO_ACTION", "reason": "Action is not BUY or SELL"}

        symbol = exec_details.get("symbol")
        total_amount = exec_details.get("amount")
        total_usd = exec_details.get("amount_usd")
        live_price = exec_details.get("price")
        
        # Determine number of slices
        num_slices = max(1, math.ceil(total_usd / self.max_child_order_usd))
        
        slice_amount = total_amount / num_slices
        child_orders = []
        
        # Simulate TWAP execution (in a real system, this would happen over hours)
        for i in range(num_slices):
            # Simulate slight price drift for each slice to mimic market movement
            drift = live_price * (0.0001 * (i - (num_slices/2))) 
            fill_price = live_price + drift if action == "BUY" else live_price - drift
            
            child_orders.append({
                "slice": i + 1,
                "amount": slice_amount,
                "fill_price": fill_price
            })
            
        avg_fill_price = sum(c["fill_price"] for c in child_orders) / num_slices
        
        result = {
            "status": "ALGO_COMPLETE",
            "algo_type": "TWAP" if num_slices > 1 else "MARKET",
            "num_slices": num_slices,
            "average_fill_price": avg_fill_price,
            "total_filled": total_amount,
            "child_orders": child_orders
        }
        
        self.memory.publish("algo_execution", result, sender="algo")
        return result
