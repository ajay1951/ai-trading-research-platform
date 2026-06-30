from crewai import Agent
from config import DATA_LLM, SPEED_LLM, REASONING_LLM
from tools.market_tools import fetch_data
from tools.news_tools import fetch_news
from tools.execution_tools import execute_order

class InstitutionalAgents:
    def data_agent(self):
        return Agent(
            role='Market Data Engineer',
            goal='Ingest and clean raw market data for {symbol} without errors.',
            backstory='You are a meticulous data engineer. You only care about accurate numbers.',
            tools=[fetch_data],
            llm=DATA_LLM,
            verbose=True
        )

    def research_agent(self):
        return Agent(
            role='Macro & Sentiment Researcher',
            goal='Scrape news for {symbol} and determine market fear/greed.',
            backstory='You are a Wall Street researcher. You detect hype and panic easily.',
            tools=[fetch_news],
            llm=SPEED_LLM,
            verbose=True
        )

    def strategy_agent(self):
        return Agent(
            role='Alpha Generation Quant',
            goal='Analyze data to generate a purely mathematical trading signal.',
            backstory='You are a math genius. You ignore news and only look at price action.',
            llm=DATA_LLM,
            verbose=True
        )

    def reasoning_agent(self):
        return Agent(
            role='Lead Portfolio Manager',
            goal='Combine the Strategy and Research reports to form a final market thesis.',
            backstory='You are the smartest person in the room. You weigh conflicting information to find the truth.',
            llm=REASONING_LLM,
            verbose=True
        )

    def risk_agent(self):
        return Agent(
            role='Chief Risk Officer (CRO)',
            goal='Review the thesis. Apply strict risk limits. Reject bad trades.',
            backstory='You are a paranoid risk manager. You demand Stop-Losses and Take-Profits. You default to HOLD if unsafe.',
            llm=REASONING_LLM,
            verbose=True
        )

    def execution_agent(self):
        return Agent(
            role='HFT Execution Server',
            goal='Take the approved order from the CRO and execute it instantly via JSON.',
            backstory='You are a machine. No emotions. You format data into JSON and execute.',
            tools=[execute_order],
            llm=SPEED_LLM,
            verbose=True
        )
    
    def supervisor_agent(self):
        return Agent(
            role='Portfolio Director & Supervisor',
            goal='Monitor all agent outputs. Request re-analysis if signals conflict. Ensure risk limits are met.',
            backstory='You are a veteran portfolio director. You coordinate agents and make final decisions.',
            llm=REASONING_LLM,
            verbose=True
        )