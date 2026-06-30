import asyncio
import json
from core.orchestrator import coordinator

async def main():
    result = await coordinator.route_query("Analyze BTC/USDT for risk and generate trading signal", {})
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
