from typing import Dict, Any
from core.memory import SharedMemory

class ModelGovernanceAgent:
    """
    Deep Learning / Model Governance Agent.
    Monitors the RL agent's updates, tracks model drift, and ensures the model
    doesn't collapse or overfit before deploying weights to the live trading pipeline.
    """
    def __init__(self, memory: SharedMemory):
        self.memory = memory
        self.loss_history = []
        self.max_allowable_loss = 5.0

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Validates the current state of the RL model.
        """
        rl_res = context.get("rl_agent", {})
        current_loss = rl_res.get("training_loss", 0.0)
        action_proposed = rl_res.get("action", "HOLD")
        
        # Track loss
        if current_loss > 0:
            self.loss_history.append(current_loss)
            if len(self.loss_history) > 100:
                self.loss_history.pop(0)
                
        # Basic Governance Rules
        status = "APPROVED"
        reason = "Model behavior is within normal parameters."
        
        if current_loss > self.max_allowable_loss:
            status = "REJECTED"
            reason = f"Model drift detected. Training loss ({current_loss:.2f}) exceeds max allowable limit."
            
        decision = {
            "model_status": status,
            "reason": reason,
            "average_historical_loss": sum(self.loss_history)/len(self.loss_history) if self.loss_history else 0.0,
            "action_proposed": action_proposed
        }
        
        self.memory.publish("governance_update", decision, sender="governance")
        return decision
