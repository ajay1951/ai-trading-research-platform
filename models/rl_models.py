import numpy as np

class NumpyPolicyNetwork:
    """
    A lightweight, numpy-based Neural Network to represent an RL Policy.
    This provides 'Deep Learning' capabilities without requiring PyTorch/TensorFlow installs.
    """
    def __init__(self, input_size: int, hidden_size: int, output_size: int):
        # Initialize weights with Xavier initialization
        self.W1 = np.random.randn(input_size, hidden_size) / np.sqrt(input_size)
        self.b1 = np.zeros(hidden_size)
        self.W2 = np.random.randn(hidden_size, output_size) / np.sqrt(hidden_size)
        self.b2 = np.zeros(output_size)
        
        # State tracking for backprop
        self.cache = {}
        
    def _relu(self, x):
        return np.maximum(0, x)
        
    def _relu_derivative(self, x):
        return (x > 0).astype(float)
        
    def forward(self, state: np.ndarray) -> np.ndarray:
        """Forward pass to predict Q-values or Action probabilities."""
        # state shape: (input_size,)
        z1 = np.dot(state, self.W1) + self.b1
        a1 = self._relu(z1)
        z2 = np.dot(a1, self.W2) + self.b2
        
        self.cache = {'state': state, 'z1': z1, 'a1': a1, 'z2': z2}
        return z2 # Q-values for actions
        
    def train_step(self, state: np.ndarray, target_q: np.ndarray, learning_rate: float = 0.01):
        """
        A single backpropagation step using MSE loss against target Q-values.
        """
        pred_q = self.forward(state)
        
        # Derivative of MSE Loss wrt pred_q
        d_z2 = 2 * (pred_q - target_q)
        
        # Backprop Layer 2
        d_W2 = np.outer(self.cache['a1'], d_z2)
        d_b2 = d_z2
        
        # Backprop Layer 1
        d_a1 = np.dot(self.W2, d_z2)
        d_z1 = d_a1 * self._relu_derivative(self.cache['z1'])
        d_W1 = np.outer(self.cache['state'], d_z1)
        d_b1 = d_z1
        
        # Gradient Descent Update
        self.W1 -= learning_rate * d_W1
        self.b1 -= learning_rate * d_b1
        self.W2 -= learning_rate * d_W2
        self.b2 -= learning_rate * d_b2
        
        return np.mean((pred_q - target_q)**2) # Return Loss

class RLEnvironment:
    """
    Mock Environment parameters for the Q-Learning formulation.
    Actions: 0: SELL, 1: HOLD, 2: BUY
    """
    ACTIONS = [0, 1, 2]
    ACTION_MAP = {0: "SELL", 1: "HOLD", 2: "BUY"}
