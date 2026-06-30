import numpy as np
import pandas as pd

class CryptoTradingEnv:
    """
    The Matrix Simulator.
    A Gymnasium-like environment that orchestrates the data and executes the trades
    determined by the Multi-Agent system. It enforces trading fees and tracks the 
    institutional portfolio value.
    """
    def __init__(self, data_df: pd.DataFrame, initial_balance=10000.0, trading_fee=0.001):
        self.df = data_df.reset_index(drop=True)
        self.initial_balance = initial_balance
        self.trading_fee = trading_fee
        self.current_step = 0
        
        # Portfolio state
        self.balance = initial_balance
        self.coin_held = 0.0
        self.portfolio_value = initial_balance
        self.portfolio_history = []

    def reset(self):
        self.current_step = 0
        self.balance = self.initial_balance
        self.coin_held = 0.0
        self.portfolio_value = self.initial_balance
        self.portfolio_history = [self.initial_balance]
        return self._get_state()

    def _get_state(self):
        row = self.df.iloc[self.current_step]
        # Return the full MTF raw quant metrics the Agents need to make decisions
        return row.to_dict()

    def step(self, final_allocation_pct):
        """
        Executes a trade based on the exact % of the portfolio to allocate to the coin.
        `final_allocation_pct` is determined by the Meta-Agent and rigorously throttled 
        by the Risk Agent's Kelly/ATR logic.
        """
        row = self.df.iloc[self.current_step]
        current_price = row['close']
        
        # 1. Target value of coins to hold based on the Agent's decision
        target_value = self.portfolio_value * final_allocation_pct
        current_value = self.coin_held * current_price
        
        # 2. Portfolio Rebalancing
        value_difference = target_value - current_value
        
        if value_difference > 0: # Buy
            amount_to_buy = value_difference / current_price
            cost = amount_to_buy * current_price
            fee = cost * self.trading_fee
            
            # Ensure we have enough cash
            if self.balance >= (cost + fee):
                self.balance -= (cost + fee)
                self.coin_held += amount_to_buy
                
        elif value_difference < 0: # Sell
            amount_to_sell = abs(value_difference) / current_price
            # Ensure we have enough coins to sell
            if amount_to_sell <= self.coin_held:
                revenue = amount_to_sell * current_price
                fee = revenue * self.trading_fee
                self.balance += (revenue - fee)
                self.coin_held -= amount_to_sell

        # 3. Fast-forward time
        self.current_step += 1
        done = self.current_step >= len(self.df) - 1
        
        # 4. Mark-to-Market Portfolio Valuation
        next_price = self.df.iloc[self.current_step]['close'] if not done else current_price
        self.portfolio_value = self.balance + (self.coin_held * next_price)
        self.portfolio_history.append(self.portfolio_value)
        
        # 5. Reward Function (Daily Return for Sharpe Ratio optimization)
        reward = (self.portfolio_value - self.portfolio_history[-2]) / self.portfolio_history[-2]
        
        return self._get_state(), reward, done, {}
        
    def get_portfolio_metrics(self):
        """
        Calculates Institutional metrics like Total Return and Sharpe Ratio.
        """
        returns = pd.Series(self.portfolio_history).pct_change().dropna()
        total_return = (self.portfolio_value - self.initial_balance) / self.initial_balance
        
        # Annualized Sharpe Ratio (Assuming 365 trading days in crypto)
        if returns.std() == 0:
            sharpe_ratio = 0.0
        else:
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(365)
            
        return {
            'final_balance': self.portfolio_value,
            'total_return_pct': total_return * 100,
            'sharpe_ratio': sharpe_ratio
        }
