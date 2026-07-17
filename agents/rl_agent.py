"""
Reinforcement Learning Agent
Uses a Deep Q-Network (implemented in numpy) to learn optimal trading strategies
and dynamically adjust parameters based on Market Regime.
"""
from core.memory import SharedMemory
from typing import Dict, Any, List
import numpy as np
import os
import json
import asyncpg
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
        
        self.db_pool = None
        self.db_setup_done = False

    async def _setup_db(self):
        if self.db_setup_done:
            return
            
        try:
            # We fetch connection parameters from env vars, matching docker-compose
            user = os.getenv("POSTGRES_USER", "financial_admin")
            password = os.getenv("POSTGRES_PASSWORD", "financial_secure_password")
            db = os.getenv("POSTGRES_DB", "ai_crypto_db")
            host = os.getenv("POSTGRES_HOST", "postgres")
            
            self.db_pool = await asyncpg.create_pool(user=user, password=password, database=db, host=host, port=5432)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS rl_transitions (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        symbol VARCHAR(20),
                        state_vector JSONB,
                        action_taken VARCHAR(10),
                        reward FLOAT,
                        next_state_vector JSONB
                    )
                ''')
            self.db_setup_done = True
            print("RL Agent PostgreSQL connected and initialized.")
        except Exception as e:
            print(f"Failed to connect to Postgres for RL Agent: {e}")

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
        
        if not self.db_setup_done:
            await self._setup_db()
            
        # Get current state
        state_vector = self._get_state_array(context)
        
        # Predict Action
        action_decision = self.predict_action(context)
        action_decision['timestamp'] = datetime.now().isoformat()
        
        # In a full system, we would calculate real reward here based on actual previous trade outcome.
        # For prototype, we generate a synthetic reward for demonstration.
        dummy_reward = float(np.random.normal(0, 0.5)) 
        
        # Log to DB
        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.execute('''
                        INSERT INTO rl_transitions (symbol, state_vector, action_taken, reward)
                        VALUES ($1, $2, $3, $4)
                    ''', symbol, json.dumps(state_vector.tolist()), action_decision['action'], dummy_reward)
            except Exception as e:
                print(f"Failed to log transition to DB: {e}")

        # Train on the current state -> next_state transition (using dummy next state for now)
        dummy_next_state = state_vector + np.random.normal(0, 0.01, self.state_size)
        action_idx = RLEnvironment.ACTIONS.index(action_decision['action'])
        self.update_model(state_vector, action_idx, dummy_reward, dummy_next_state)

        self.memory.store(f"rl_decision:{symbol}", action_decision, agent="rl_agent", publish_update=True)
        return action_decision