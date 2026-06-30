from crewai import Task

class InstitutionalTasks:
    def data_task(self, agent, symbol):
        return Task(
            description=f'Fetch and clean market data for {symbol}.',
            expected_output='A clean summary of prices and 24h volume.',
            agent=agent
        )

    def research_task(self, agent, symbol):
        return Task(
            description=f'Search the web for the latest news on {symbol}. Is the sentiment Bullish, Bearish, or Neutral?',
            expected_output='A paragraph summarizing current market sentiment.',
            agent=agent
        )

    def strategy_task(self, agent, symbol):
        return Task(
            description=f'Based on the market data, calculate momentum. Is price moving up or down? Generate a technical signal.',
            expected_output='A technical signal: BULLISH, BEARISH, or CHOPPY.',
            agent=agent
        )

    def reasoning_task(self, agent, symbol):
        return Task(
            description=f'Read the Technical Signal and the Sentiment Report for {symbol}. Debate if they align. Formulate a final thesis to Buy, Sell, or Hold.',
            expected_output='A well-reasoned paragraph concluding with a directional thesis.',
            agent=agent
        )

    def risk_task(self, agent, symbol):
        return Task(
            description=f'Review the Thesis for {symbol}. If the thesis says BUY or SELL, calculate a logical Stop Loss and Take Profit price based on recent highs/lows. If unsafe, output HOLD.',
            expected_output='A strict risk mandate specifying Action, Stop-Loss, and Take-Profit.',
            agent=agent
        )

    def execution_task(self, agent, symbol):
        return Task(
            description=(
                f'Read the Risk Mandate. Use the Execution tool to place the paper trade. '
                f'You MUST pass a valid JSON string to the tool like this: '
                f'{{"action": "BUY", "symbol": "{symbol}", "stop_loss": 50000, "take_profit": 60000}}'
            ),
            expected_output='The success message from the Execution tool.',
            agent=agent
        )
    
    def supervise_task(self, agent, symbol):
        return Task(
            description=(
                f'Review all outputs from Data, Research, Strategy, Reasoning, Risk, and Execution agents. '
                f'If the Technical Signal and Sentiment report conflict significantly, request re-analysis. '
                f'Validate that Stop-Loss and Take-Profit are within acceptable ranges. '
                f'Output a final coordination decision and summary for {symbol}.'
            ),
            expected_output='A supervisor report confirming all checks passed or requesting re-analysis.',
            agent=agent
        )