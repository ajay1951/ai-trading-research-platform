import torch
import torch.nn as nn
import torch.optim as optim
import random
import numpy as np
from collections import deque
import math

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=5000):
        super(PositionalEncoding, self).__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1) # [max_len, 1, d_model]
        self.register_buffer('pe', pe)

    def forward(self, x):
        # x shape: [seq_len, batch_size, d_model]
        x = x + self.pe[:x.size(0), :]
        return x

class TransformerQNetwork(nn.Module):
    def __init__(self, input_dim, d_model, nhead, num_layers, output_dim, seq_len):
        super(TransformerQNetwork, self).__init__()
        self.d_model = d_model
        
        # Linear projection from raw features to d_model space
        self.input_linear = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        
        encoder_layers = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, dim_feedforward=d_model*4, dropout=0.1)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layers, num_layers=num_layers)
        
        # Map the final output sequence to the Q-values
        self.fc_out = nn.Sequential(
            nn.Linear(d_model * seq_len, d_model),
            nn.ReLU(),
            nn.Linear(d_model, output_dim)
        )

    def forward(self, x):
        # x shape: [batch_size, seq_len, input_dim]
        # Transformer expects [seq_len, batch_size, d_model]
        x = self.input_linear(x) * math.sqrt(self.d_model)
        x = x.transpose(0, 1) 
        x = self.pos_encoder(x)
        
        output = self.transformer_encoder(x) # [seq_len, batch_size, d_model]
        
        # Flatten and feed into FC layer
        output = output.transpose(0, 1).flatten(start_dim=1) # [batch_size, seq_len * d_model]
        return self.fc_out(output)

class TransformerMetaAgent:
    """
    Hedge Fund Tier AI. 
    Processes sequential state vectors to predict Q-values using Self-Attention.
    """
    def __init__(self, input_dim=19, seq_len=10, d_model=64, nhead=4, num_layers=2, output_dim=3, lr=0.0005, gamma=0.99, buffer_size=50000, batch_size=256):
        self.input_dim = input_dim
        self.seq_len = seq_len
        self.output_dim = output_dim
        self.gamma = gamma
        self.batch_size = batch_size
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[Transformer] Initializing on device: {self.device} | Sequence Window: {self.seq_len}")
        
        self.q_network = TransformerQNetwork(input_dim, d_model, nhead, num_layers, output_dim, seq_len).to(self.device)
        self.target_network = TransformerQNetwork(input_dim, d_model, nhead, num_layers, output_dim, seq_len).to(self.device)
        self.update_target_network()
        
        self.optimizer = optim.Adam(self.q_network.parameters(), lr=lr)
        self.loss_fn = nn.SmoothL1Loss() # Huber Loss for better stability with outliers
        
        self.memory = deque(maxlen=buffer_size)

    def update_target_network(self):
        self.target_network.load_state_dict(self.q_network.state_dict())

    def remember(self, state_sequence, action, reward, next_state_sequence, done):
        """Stores a FULL SEQUENCE of states, not just a single state"""
        self.memory.append((state_sequence, action, reward, next_state_sequence, done))

    def get_action(self, state_sequence, epsilon=0.0):
        if random.random() < epsilon:
            return random.randint(0, self.output_dim - 1)
            
        with torch.no_grad():
            # state_sequence is [seq_len, input_dim]
            state_tensor = torch.FloatTensor(np.array(state_sequence)).unsqueeze(0).to(self.device)
            q_values = self.q_network(state_tensor)
            return torch.argmax(q_values).item()

    def train_step(self):
        if len(self.memory) < self.batch_size:
            return 0.0
            
        batch = random.sample(self.memory, self.batch_size)
        
        # Extract sequences: [batch_size, seq_len, input_dim]
        states = torch.FloatTensor(np.array([x[0] for x in batch])).to(self.device)
        actions = torch.LongTensor(np.array([x[1] for x in batch])).unsqueeze(1).to(self.device)
        rewards = torch.FloatTensor(np.array([x[2] for x in batch])).unsqueeze(1).to(self.device)
        next_states = torch.FloatTensor(np.array([x[3] for x in batch])).to(self.device)
        dones = torch.FloatTensor(np.array([x[4] for x in batch])).unsqueeze(1).to(self.device)
        
        current_q_values = self.q_network(states).gather(1, actions)
        
        with torch.no_grad():
            next_actions = self.q_network(next_states).argmax(1, keepdim=True)
            target_next_q_values = self.target_network(next_states).gather(1, next_actions)
            
        target_q_values = rewards + (self.gamma * target_next_q_values * (1 - dones))
        
        loss = self.loss_fn(current_q_values, target_q_values)
        self.optimizer.zero_grad()
        loss.backward()
        
        # Gradient Clipping for Transformer stability
        torch.nn.utils.clip_grad_norm_(self.q_network.parameters(), max_norm=1.0)
        self.optimizer.step()
        
        return loss.item()
