import torch
import torch.nn as nn
import torch.optim as optim
import random
import numpy as np
from collections import deque

class QNetwork(nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim):
        super(QNetwork, self).__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim)
        )
    def forward(self, x):
        return self.network(x)

class MetaAgent:
    """
    The General (Double Deep Q-Network).
    Receives probabilities from Quant and Sentiment, outputs Portfolio Weights.
    Uses a Target Network and Replay Buffer for institutional stability.
    """
    def __init__(self, input_dim=3, hidden_dim=64, output_dim=3, lr=0.001, gamma=0.99, buffer_size=10000, batch_size=64):
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.gamma = gamma
        self.batch_size = batch_size
        
        # GPU Acceleration
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[PyTorch] Using device: {self.device}")
        
        # Double DQN Networks
        self.q_network = QNetwork(input_dim, hidden_dim, output_dim).to(self.device)
        self.target_network = QNetwork(input_dim, hidden_dim, output_dim).to(self.device)
        self.update_target_network() # Sync weights initially
        
        self.optimizer = optim.Adam(self.q_network.parameters(), lr=lr)
        self.loss_fn = nn.MSELoss()
        
        # Replay Buffer
        self.memory = deque(maxlen=buffer_size)

    def update_target_network(self):
        """Copies the Main Q-Network weights to the Target Network"""
        self.target_network.load_state_dict(self.q_network.state_dict())

    def remember(self, state, action, reward, next_state, done):
        """Stores experience in the Replay Buffer"""
        self.memory.append((state, action, reward, next_state, done))

    def get_action(self, state, epsilon=0.0):
        """Epsilon-Greedy Action Selection"""
        if random.random() < epsilon:
            return random.randint(0, self.output_dim - 1)
            
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.q_network(state_tensor)
            return torch.argmax(q_values).item()

    def train_step(self):
        """
        The Core Backpropagation Math.
        Samples a batch from memory and trains the Double DQN.
        """
        if len(self.memory) < self.batch_size:
            return 0.0 # Not enough memories yet
            
        # 1. Sample random batch from memory
        batch = random.sample(self.memory, self.batch_size)
        
        states = torch.FloatTensor(np.array([x[0] for x in batch])).to(self.device)
        actions = torch.LongTensor(np.array([x[1] for x in batch])).unsqueeze(1).to(self.device)
        rewards = torch.FloatTensor(np.array([x[2] for x in batch])).unsqueeze(1).to(self.device)
        next_states = torch.FloatTensor(np.array([x[3] for x in batch])).to(self.device)
        dones = torch.FloatTensor(np.array([x[4] for x in batch])).unsqueeze(1).to(self.device)
        
        # 2. Compute current Q-values from the Main Network
        current_q_values = self.q_network(states).gather(1, actions)
        
        # 3. DOUBLE DQN LOGIC
        # Use Main Network to select the best action for the next state
        with torch.no_grad():
            next_actions = self.q_network(next_states).argmax(1, keepdim=True)
            # Use Target Network to evaluate that action
            target_next_q_values = self.target_network(next_states).gather(1, next_actions)
            
        # 4. Bellman Equation: Target = Reward + Gamma * Q(Next State)
        target_q_values = rewards + (self.gamma * target_next_q_values * (1 - dones))
        
        # 5. Backpropagation
        loss = self.loss_fn(current_q_values, target_q_values)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        return loss.item()
