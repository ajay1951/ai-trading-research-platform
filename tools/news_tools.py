from langchain_community.tools import DuckDuckGoSearchRun
from crewai.tools import BaseTool

search = DuckDuckGoSearchRun()

class FetchNewsTool(BaseTool):
    name: str = "Search Crypto News"
    description: str = "Search the web for the latest news about a specific cryptocurrency."
    
    def _run(self, symbol: str) -> str:
        try:
            results = search.run(f"latest news {symbol} crypto market")
            return results
        except Exception as e:
            return ""

fetch_news = FetchNewsTool()