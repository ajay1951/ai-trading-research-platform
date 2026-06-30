import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BacktestLab")

class StatArbBacktester:
    """
    Offline Out-of-Sample Validation Environment for Statistical Arbitrage.
    Rigidly splits data and enforces hardcoded mathematical penalties (fees, slippage)
    to prevent look-ahead bias and simulate realistic execution.
    """
    
    def __init__(self, data_df: pd.DataFrame, z_threshold: float = 2.0, window: int = 20):
        """
        data_df: A merged DataFrame containing 'close_A' and 'close_B'
        """
        self.data = data_df.copy()
        self.z_threshold = z_threshold
        self.window = window
        
        # --- HARDCODED MATHEMATICAL PENALTIES ---
        self.taker_fee = 0.001       # 0.1% taker fee per trade
        self.pip_size = 0.0001       # Standard pip definition
        self.slippage_pips = 2       # 2 pips slippage
        self.slippage_cost = self.slippage_pips * self.pip_size

    @staticmethod
    def load_and_split_data(csv_a: str, csv_b: str, train_ratio: float = 0.7):
        """
        Ingests historical OHLCV CSV data for two assets and rigidly splits 
        it into a 70% training set and a 30% blind testing set.
        """
        try:
            df_a = pd.read_csv(csv_a, index_col=0, parse_dates=True)
            df_b = pd.read_csv(csv_b, index_col=0, parse_dates=True)
            
            # Inner join ensures no look-ahead or timestamp mismatch
            df = df_a[['close']].join(df_b[['close']], lsuffix='_A', rsuffix='_B', how='inner').dropna()
            
            split_idx = int(len(df) * train_ratio)
            train_set = df.iloc[:split_idx]
            test_set = df.iloc[split_idx:]
            
            logger.info(f"Data split rigidly: {len(train_set)} train rows (70%), {len(test_set)} test rows (30%).")
            return train_set, test_set
        except Exception as e:
            logger.error(f"Failed to load or split data: {e}")
            # Return dummy data for illustration if CSVs aren't found
            logger.info("Generating synthetic data for demonstration purposes...")
            dates = pd.date_range("2024-01-01", periods=1000, freq='h')
            np.random.seed(42)
            prices_a = np.cumsum(np.random.randn(1000) * 10) + 50000
            # Asset B is cointegrated with A
            prices_b = prices_a * 0.05 + np.random.randn(1000) * 5
            
            df = pd.DataFrame({'close_A': prices_a, 'close_B': prices_b}, index=dates)
            split_idx = int(len(df) * train_ratio)
            return df.iloc[:split_idx], df.iloc[split_idx:]

    def run_backtest(self) -> dict:
        """
        Pure Pandas/NumPy vector-based backtest loop for the Z-score spread strategy.
        Applies strict penalties and returns a tear sheet.
        """
        df = self.data.copy()
        
        # 1. Strategy Mathematical Core (Cointegration Spread)
        df['spread'] = df['close_A'] - df['close_B']
        df['mean'] = df['spread'].rolling(window=self.window).mean()
        df['std'] = df['spread'].rolling(window=self.window).std()
        
        # Avoid division by zero
        df['std'] = df['std'].replace(0, np.nan)
        df['zscore'] = (df['spread'] - df['mean']) / df['std']
        
        # 2. Vectorized Signal Generation
        df['position'] = np.nan
        # Z > threshold -> SHORT A / LONG B (Short the spread -> position = -1)
        df.loc[df['zscore'] >= self.z_threshold, 'position'] = -1
        # Z < -threshold -> LONG A / SHORT B (Long the spread -> position = 1)
        df.loc[df['zscore'] <= -self.z_threshold, 'position'] = 1
        # Mean reversion (Z near 0) -> Close out positions
        df.loc[df['zscore'].between(-0.5, 0.5), 'position'] = 0
        
        # Forward fill the position to hold it over time
        df['position'] = df['position'].ffill().fillna(0)
        
        # 3. Vectorized Returns 
        df['return_A'] = df['close_A'].pct_change()
        df['return_B'] = df['close_B'].pct_change()
        
        # Strategy Return: if position=1, we gain when A goes up and B goes down
        df['spread_return'] = df['return_A'] - df['return_B']
        df['gross_return'] = df['position'].shift(1) * df['spread_return']
        
        # 4. Apply Hardcoded Mathematical Penalties
        # Calculate how many times we traded (position changes)
        df['trade'] = df['position'].diff().fillna(0)
        
        # Slippage in pct terms for asset A and B
        slippage_cost_pct_A = self.slippage_cost / df['close_A']
        slippage_cost_pct_B = self.slippage_cost / df['close_B']
        
        # Total transaction cost per trade unit (x2 because we trade both legs of the pair)
        # Entry/Exit incurs 0.1% taker fee + 2 pips slippage
        df['transaction_costs'] = df['trade'].abs() * ((self.taker_fee * 2) + slippage_cost_pct_A + slippage_cost_pct_B)
        
        # Net Return
        df['net_return'] = df['gross_return'].fillna(0) - df['transaction_costs'].fillna(0)
        
        # 5. Calculate Tear Sheet Metrics
        df['cum_return'] = (1 + df['net_return']).cumprod() - 1
        total_return = df['cum_return'].iloc[-1] if not df.empty else 0
        
        # Max Drawdown
        roll_max = (1 + df['net_return']).cumprod().cummax()
        drawdown = (1 + df['net_return']).cumprod() / roll_max - 1.0
        max_drawdown = drawdown.min()
        
        # Sharpe Ratio (Assuming hourly data, roughly 8760 periods/year)
        risk_free_rate = 0.0
        annualized_volatility = df['net_return'].std() * np.sqrt(8760)
        annualized_return = df['net_return'].mean() * 8760
        sharpe_ratio = (annualized_return - risk_free_rate) / (annualized_volatility + 1e-9)
        
        # Win Rate (Trade-level or period-level)
        winning_periods = (df['net_return'] > 0).sum()
        losing_periods = (df['net_return'] < 0).sum()
        win_rate = winning_periods / (winning_periods + losing_periods) if (winning_periods + losing_periods) > 0 else 0
        
        tear_sheet = {
            "Total Return": f"{total_return * 100:.2f}%",
            "Max Drawdown": f"{max_drawdown * 100:.2f}%",
            "Sharpe Ratio": f"{sharpe_ratio:.2f}",
            "Win Rate": f"{win_rate * 100:.2f}%",
            "Total Trades": int(df['trade'].abs().sum()),
            "Total Penalties Paid": f"-{(df['transaction_costs'].sum() * 100):.2f}%"
        }
        
        return tear_sheet, df

if __name__ == "__main__":
    # Demonstration execution
    train_data, test_data = StatArbBacktester.load_and_split_data("dummy_a.csv", "dummy_b.csv")
    
    logger.info("Running In-Sample (Training) Backtest...")
    train_bt = StatArbBacktester(train_data)
    train_metrics, _ = train_bt.run_backtest()
    logger.info(f"Training Results: {train_metrics}")
    
    logger.info("Running Out-of-Sample (Blind Testing) Backtest...")
    test_bt = StatArbBacktester(test_data)
    test_metrics, _ = test_bt.run_backtest()
    logger.info(f"Test Results: {test_metrics}")
