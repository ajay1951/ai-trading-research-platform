"""
Reinforcement Learning Agent
Uses a Deep Q-Network (implemented in numpy) to learn optimal trading strategies
and dynamically adjust parameters based on Market Regime.
"""
from core.memory import SharedMemory
from typing import Dict, Any, List
import numpy as np
from datetime import datetime
from models.rl_models import NumpyPolicyNetwork, RLEnvironment

class RLAgent:
    """
    RL Agent using a Numpy-based Neural Network to output Q-Values for actions.
    """
    def __init__(self, memory: SharedMemory):
        self.memory = memory
        
        # State: [quant_signal, sentiment, risk, volatility, trend_feature, vol_feature] -> 6 inputs
        self.state_size = 6
        self.hidden_size = 12
        self.action_size = len(RLEnvironment.ACTIONS) # 0: SELL, 1: HOLD, 2: BUY
        
        self.policy_net = NumpyPolicyNetwork(self.state_size, self.hidden_size, self.action_size)
        self.is_trained = True 
        self.last_loss = 0.0

    def _get_state_array(self, context: Dict) -> np.ndarray:
        """
        Extracts and normalizes numerical features into a numpy array for the NN.
        """
        quant_analysis = context.get("quant", {}).get("analysis", {})
        quant_signal = quant_analysis.get("signal", {})
        research_analysis = context.get("research", {}).get("research", {})
        market_regime = context.get("regime", {}).get("regime", {})
        risk_analysis = context.get("risk", {}).get("risk_assessment", {})

        quant_signal_val = 0
        if quant_signal.get("signal") == "BUY":
            quant_signal_val = 1
        elif quant_signal.get("signal") == "SELL":
            quant_signal_val = -1

        sentiment_score = research_analysis.get("macro_sentiment", {}).get("sentiment_score", 0.0)
        
        risk_map = {"LOW": 0.0, "MEDIUM": 0.5, "HIGH": 1.0}
        risk_level = risk_map.get(risk_analysis.get("risk_level", "MEDIUM"), 0.5)

        volatility = risk_analysis.get("var", {}).get("var", 2.5) / 10.0 

        # Regime features
        trend_feature = 1.0 if "BULL" in market_regime.get("state", "") else -1.0
        vol_feature = 1.0 if "HIGH_VOL" in market_regime.get("state", "") else 0.0

        state = np.array([
            quant_signal.get("confidence", 0.5) * quant_signal_val,
            sentiment_score,
            risk_level,
            volatility,
            trend_feature,
            vol_feature
        ])
        return state

    def update_model(self, state: np.ndarray, action_idx: int, reward: float, next_state: np.ndarray):
        """
        Conceptually performs a Q-learning Bellman update.
        """
        gamma = 0.95
        current_q = self.policy_net.forward(state)
        next_q = self.policy_net.forward(next_state)
        
        target_q = np.copy(current_q)
        target_q[action_idx] = reward + gamma * np.max(next_q)
        
        loss = self.policy_net.train_step(state, target_q)
        self.last_loss = float(loss)

    def predict_action(self, context: Dict) -> Dict:
        """
        Predicts the optimal action using the Q-Network.
        """
        state = self._get_state_array(context)
        q_values = self.policy_net.forward(state)
        
        best_action_idx = int(np.argmax(q_values))
        action_name = RLEnvironment.ACTION_MAP[best_action_idx]
        
        # Softmax for confidence
        exp_q = np.exp(q_values - np.max(q_values))
        probs = exp_q / np.sum(exp_q)
        confidence = float(probs[best_action_idx])
        
        # Adaptive Sizing based on Q-value magnitude
        sizing_factor = max(0.2, min(1.5, float(q_values[best_action_idx])))

        return {
            "action": action_name,
            "sizing_factor": round(sizing_factor, 2),
            "confidence": round(confidence, 2),
            "q_values": q_values.tolist(),
            "reason": f"DQN predicts {action_name} with {confidence*100:.1f}% confidence.",
            "training_loss": self.last_loss
        }

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        symbol = parameters.get("symbol", "BTC/USDT")
        
        # In a full system, we would fetch the last state/action/reward here and train
        # For prototype, we do a forward pass to get the decision.
        action_decision = self.predict_action(context)
        action_decision['timestamp'] = datetime.now().isoformat()

        self.memory.store(f"rl_decision:{symbol}", action_decision, agent="rl_agent", publish_update=True)
        return action_decision