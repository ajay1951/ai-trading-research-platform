"""
Enhanced Dashboard API with advanced visualization and NL query support.
Premium dark trading terminal with glassmorphism and micro-interactions.
"""
import logging
import json
import asyncio
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pathlib import Path
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import redis.asyncio as redis
import uvicorn
import ccxt.async_support as ccxt_async
import threading
import aiohttp
from core.orchestrator import coordinator
from core.nl_interface import nl_interface
from core.memory import get_memory
global_memory = get_memory()
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

# Global exchange instance for live ticker updates
exchange_for_ticker = None
exchange_pool: Dict[str, ccxt_async.Exchange] = {}
is_redis_connected = False
redis_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup initiated.")
    global exchange_for_ticker, exchange_pool, redis_client, is_redis_connected

    # Initialize a pool of exchanges to be reused
    exchange_ids = ['binance', 'kraken', 'kucoin']
    for eid in exchange_ids:
        exchange = None  # Ensure exchange is defined for the finally block
        try:
            exchange_class = getattr(ccxt_async, eid)
            config = {'enableRateLimit': True}
            if eid == 'binance' and os.getenv('BINANCE_API_KEY') and os.getenv('BINANCE_API_SECRET'):
                config['apiKey'] = os.getenv('BINANCE_API_KEY')
                config['secret'] = os.getenv('BINANCE_API_SECRET')

            exchange = exchange_class(config)
            await exchange.load_markets()  # Pre-load markets to avoid doing it on first request
            exchange_pool[eid] = exchange
            logger.info(f"Initialized and loaded markets for {eid}")
        except Exception as e:
            logger.error(f"Failed to initialize exchange {eid}: {e}")
            if exchange:
                await exchange.close()

    # Set the primary exchange for the live ticker broadcast
    if 'binance' in exchange_pool:
        exchange_for_ticker = exchange_pool['binance']
    elif exchange_pool:
        exchange_for_ticker = next(iter(exchange_pool.values()))

    # Initialize Redis client for Pub/Sub
    try:
        redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connection successful for dashboard.")
        is_redis_connected = True
    except Exception as e:
        logger.error(f"Dashboard could not connect to Redis: {e}")
        redis_client = None
        is_redis_connected = False

    dashboard_state.is_running = True
    broadcast_task = asyncio.create_task(broadcast_updates())

    # Start the Redis listener task
    redis_listener_task = None
    if redis_client:
        redis_listener_task = asyncio.create_task(redis_listener())

    # Start the SRE heartbeat monitor task
    heartbeat_task = asyncio.create_task(heartbeat_monitor())

    yield
    logger.info("Application shutdown initiated.")
    # Close all exchanges in the pool
    for exchange in exchange_pool.values():
        if exchange:
            await exchange.close()

    dashboard_state.is_running = False
    broadcast_task.cancel()
    heartbeat_task.cancel()
    if redis_listener_task:
        redis_listener_task.cancel()

    try:
        await broadcast_task
        await heartbeat_task
        if redis_listener_task:
            await redis_listener_task
    except asyncio.CancelledError:
        logger.info("Tasks cancelled successfully.")
    logger.info("Application shutdown complete.")

app = FastAPI(title="Multi-Agent Financial Intelligence Dashboard", lifespan=lifespan)


# Define project root for path calculations
PROJECT_ROOT = Path(__file__).parent.parent

# Mount static files directory, assuming it's at the project root.
if os.path.isdir(PROJECT_ROOT / "static"):
    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")


def _format_trade_setup_for_log(setup: Dict, name: str) -> List[str]:
    """Formats a single trade setup for logging."""
    if not setup or not setup.get("direction") or setup.get("direction") == "Neutral":
        return [f"• {name}: No actionable setup available."]
    
    lines = []
    direction = setup.get('direction', 'N/A')
    entry = setup.get('entry_zone', 'N/A')
    sl = setup.get('stop_loss', 'N/A')
    rr = setup.get('risk_reward_ratio', 'N/A')
    conf = setup.get('confidence_score', 0) * 100
    
    lines.append(f"• {name}: {direction} @ {entry} (SL: {sl})")
    lines.append(f"  -> R/R: {rr}, Confidence: {conf:.0f}%")
    lines.append(f"  -> TPs: {setup.get('tp1', 'N/A')}, {setup.get('tp2', 'N/A')}, {setup.get('tp3', 'N/A')}")
    lines.append(f"  -> Reason: {setup.get('reasoning', 'N/A')}")
    return lines


def _format_analysis_for_log(result_dict: Dict) -> str:
    """Formats the new trade roadmap dictionary into a readable log string."""
    
    # The result from the coordinator might be nested. Find the actual roadmap.
    # The multistyle agent is expected to return the final roadmap structure.
    roadmap = result_dict.get("results", {}).get("multistyle", {})
    if not roadmap or "scalping" not in roadmap:
        roadmap = result_dict.get("results", {}).get("supervisor", {})
        if not roadmap or "scalping" not in roadmap:
            roadmap = result_dict # Assume it's already the roadmap

    if "scalping" not in roadmap:
        return f"Analysis Result (Legacy or Incomplete): {json.dumps(result_dict, indent=2, default=str)}"

    output = ["============================================================",
              "INSTITUTIONAL TRADE PLAN REPORT",
              f"Timestamp: {roadmap.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
              f"Symbol: {roadmap.get('symbol', 'N/A')}",
              "============================================================"]

    summary = roadmap.get('summary', {})
    output.append("\n[EXECUTIVE SUMMARY]")
    output.append(f"• Market Bias: {summary.get('market_bias', 'N/A')}")
    output.append(f"• Market Regime: {summary.get('market_regime', 'N/A')}")
    output.append(f"• Best Current Opportunity: {summary.get('best_current_opportunity', 'N/A')}")
    output.append(f"• Highest Confidence Setup: {summary.get('highest_confidence_setup', 'N/A')}")
    output.append(f"• Key Risk Factors: {summary.get('key_risk_factors', 'N/A')}")

    # --- Trading Styles ---
    styles = ["scalping", "intraday", "swing", "position"]
    for style in styles:
        style_data = roadmap.get(style)
        if style_data:
            output.append(f"\n[{style.upper()} TRADING PLAN]")
            output.extend(_format_trade_setup_for_log(style_data.get('immediate_trade'), "Immediate Trade"))
            output.extend(_format_trade_setup_for_log(style_data.get('next_trade', style_data.get('future_trade')), "Next/Future Trade"))
            output.extend(_format_trade_setup_for_log(style_data.get('alternative_trade'), "Alternative Trade"))
            output.extend(_format_trade_setup_for_log(style_data.get('recovery_trade'), "Recovery Trade"))

    # --- Rankings ---
    rankings = roadmap.get('rankings', {})
    if rankings:
        output.append("\n[OPPORTUNITY RANKINGS]")
        for key, value in rankings.items():
            title = key.replace('_', ' ').title()
            if isinstance(value, dict):
                conf_score = value.get('confidence_score', 0) * 100
                output.append(f"• {title}: {value.get('style', 'N/A').title()} {value.get('direction', '')} (Conf: {conf_score:.0f}%)")
            else:
                output.append(f"• {title}: {value}")

    return "\n".join(output)


# ============ Pydantic Models ============

class NLQueryRequest(BaseModel):
    query: str
    context: Optional[Dict] = None


class NLQueryResponse(BaseModel):
    intent: str
    entities: Dict
    result: Dict
    formatted_output: str


class ExternalAgentQueryRequest(BaseModel):
    agent_id: str
    query: str
    context: Optional[Dict] = None

class AgentCapabilityResponse(BaseModel):
    name: str
    description: str
    supported_operations: List[str]
    dependencies: List[str]


class VisualizationDataRequest(BaseModel):
    symbol: str
    data_type: str = "price"  # price, indicators, sentiment, risk
    timeframe: str = "1d"

# ============ Dashboard State ============

class DashboardState:
    def __init__(self):
        self.current_symbol: Optional[str] = None
        self.query_history: List[Dict] = []
        self.agent_states: Dict[str, Dict] = {}
        self.latest_results: Dict = {}
        self.is_running: bool = False
        self.live_price_data: Optional[Dict] = None


dashboard_state = DashboardState()


# ============ WebSocket Manager ============

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict):
        # Iterate over a copy of the list to allow safe removal during iteration
        for connection in self.active_connections[:]:
            try:
                await connection.send_json(message)
            except Exception as e:
                # A client has disconnected. This is expected, so we just remove them.
                self.disconnect(connection)


manager = ConnectionManager()

async def redis_listener():
    """Listens to Redis Pub/Sub for real-time data and broadcasts alerts to clients."""
    if not redis_client:
        logger.warning("Redis client not available. Real-time candle updates are disabled.")
        return

    pubsub = redis_client.pubsub()
    # Subscribe to all 1m market data channels
    await pubsub.psubscribe("market_data:1m:*")
    logger.info("Subscribed to Redis channel 'market_data:1m:*'")

    while dashboard_state.is_running:
        try:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "pmessage":
                data = json.loads(message['data'])
                symbol = data.get('symbol')

                # If the new candle is for the currently viewed symbol, notify the frontend
                if symbol == dashboard_state.current_symbol:
                    logger.debug(f"Received new candle for {symbol} from Redis. Broadcasting alert.")
                    await manager.broadcast({"type": "new_candle_alert", "symbol": symbol})
        except asyncio.CancelledError:
            logger.info("Redis listener task cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in redis_listener: {e}")
            await asyncio.sleep(5) # Avoid fast error loops

# ============ Real-time Update Loop ============

async def heartbeat_monitor():
    """SRE daemon to monitor trading loop health and send external pings."""
    ping_url = os.getenv("UPTIME_PING_URL")
    if not ping_url:
        logger.warning("UPTIME_PING_URL not set. Heartbeat monitor is disabled.")
        return
        
    logger.info(f"Starting SRE Heartbeat Monitor. Pinging: {ping_url}")
    
    async with aiohttp.ClientSession() as session:
        while dashboard_state.is_running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                last_active = global_memory.get("last_active_timestamp")
                if last_active is None:
                    logger.debug("Heartbeat: Waiting for trading loop to initialize...")
                    continue
                    
                delta_seconds = datetime.now().timestamp() - float(last_active)
                
                if delta_seconds > 60:
                    logger.critical(f"🚨 SRE ALERT: Trading loop frozen! No activity for {delta_seconds:.1f}s. Halting heartbeat ping.")
                    # By NOT sending the ping, the external service will trigger its alert
                else:
                    # System is healthy, ping the external uptime service
                    async with session.get(ping_url) as response:
                        if response.status not in (200, 201, 202):
                            logger.error(f"Heartbeat ping failed with status: {response.status}")
                        else:
                            logger.debug("Heartbeat ping successful.")
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat_monitor: {e}")

async def broadcast_updates():
    """Continuously broadcast dashboard state updates."""
    while True:
        try:
            await asyncio.sleep(2) # Slower refresh to respect rate limits
            
            # Gather current agent states
            agent_states = dashboard_state.agent_states.copy()
            for name in coordinator._agents:
                if name not in agent_states:
                    agent_states[name] = {
                        "status": global_memory.get(f"agent:{name}:status", "idle"),
                        "last_update": datetime.now().isoformat()
                    }
            
            # Fetch live price for the current symbol
            live_price_data = None
            symbol = dashboard_state.current_symbol
            try:
                if symbol and '/' in symbol and exchange_for_ticker:
                    ticker = await exchange_for_ticker.fetch_ticker(symbol)
                    live_price_data = {
                        'price': ticker.get('last'),
                        'change_pct': ticker.get('percentage'),
                        'high': ticker.get('high'),
                        'low': ticker.get('low'),
                    }
                    dashboard_state.live_price_data = live_price_data
            except Exception as e:
                logger.warning(f"Live price fetch failed for {symbol}: {type(e).__name__}: {e}") # Changed to warning for visibility
            
            if live_price_data is None and symbol:
                try:
                    def fetch_yf():
                        import yfinance as yf
                        yf_symbol = symbol.replace('/', '-')
                        if yf_symbol.endswith('-USDT'):
                            yf_symbol = yf_symbol.replace('-USDT', '-USD')
                        ticker = yf.Ticker(yf_symbol)
                        todays_data = ticker.history(period='2d')
                        if len(todays_data) >= 1:
                            price = float(todays_data['Close'].iloc[-1])
                            high = float(todays_data['High'].iloc[-1])
                            low = float(todays_data['Low'].iloc[-1])
                            change = 0.0
                            if len(todays_data) >= 2:
                                prev = float(todays_data['Close'].iloc[-2])
                                change = ((price - prev) / prev) * 100.0
                            return {'price': price, 'change_pct': change, 'high': high, 'low': low}
                        return None
                    live_price_data = await asyncio.to_thread(fetch_yf)
                    if live_price_data:
                        dashboard_state.live_price_data = live_price_data
                except Exception as yf_e:
                    logger.warning(f"yfinance fallback live price fetch failed for {symbol}: {yf_e}")
            
            # Check the status of exchange connections
            exchange_status = {
                'binance': 'binance' in exchange_pool,
                'kraken': 'kraken' in exchange_pool,
                'kucoin': 'kucoin' in exchange_pool,
            }

            # Build update message
            update = {
                "type": "dashboard_update",
                "timestamp": datetime.now().isoformat(),
                "symbol": dashboard_state.current_symbol,
                "agents": agent_states,
                "latest_results": dashboard_state.latest_results,
                "query_count": len(dashboard_state.query_history),
                "live_price": live_price_data,
                "is_redis_connected": is_redis_connected,
                "exchange_status": exchange_status
            }
            
            await manager.broadcast(update)
        except asyncio.CancelledError:
            logger.info("Broadcast updates task cancelled.")
            break # Exit the loop when cancelled
        except Exception as e:
            logger.error("Error in broadcast_updates: %s", e)


# ============ Routes ============

@app.get("/")
async def get_dashboard():
    """Serve the enhanced dashboard HTML."""
    # The dashboard HTML is now located in the same directory as this server file.
    dashboard_path = Path(__file__).parent / "index.html"
    if not dashboard_path.is_file():
        logger.error(f"Dashboard template not found at {dashboard_path}")
        raise HTTPException(
            status_code=500, detail="Dashboard template (index.html) not found."
        )
    return HTMLResponse(content=dashboard_path.read_text())


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Silently handle favicon requests to prevent 404 logs."""
    return Response(status_code=204)

@app.get("/health")
async def health_check():
    """Simple health check endpoint for container monitoring."""
    return {"status": "ok"}


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools():
    """Silently handle Chrome devtools requests to prevent 404 logs."""
    return Response(status_code=204)

@app.post("/api/query")
async def process_nl_query(request: NLQueryRequest):
    """
    Process natural language query through orchestrator.
    """
    try:
        # Parse query
        parsed = nl_interface.parse_query(request.query)
        
        query_context = request.context or {}
        
        # Ensure 'strategy' is removed to always trigger the full multi-style analysis
        if 'strategy' in query_context:
            del query_context['strategy']
        
        # Fetch live price for the specific symbol in the query for real-time analysis.
        # This is more robust than relying on the broadcast loop's state.
        query_symbol = parsed.entities.get("symbol")
        if query_symbol:
            dashboard_state.current_symbol = query_symbol
        else:
            query_symbol = dashboard_state.current_symbol
            
        if query_symbol:
            try:
                logger.debug(f"Fetching live price for {query_symbol} on-demand...")
                ticker = await exchange_for_ticker.fetch_ticker(query_symbol)
                live_price = ticker.get('last')
                if live_price is not None:
                    query_context['live_price'] = live_price
                    logger.debug(f"Live price {live_price} for {query_symbol} added to context.")
            except Exception as e:
                logger.warning(f"On-demand live price fetch for {query_symbol} failed: {e}")

        # Route through orchestrator
        result = await coordinator.route_query(request.query, context=query_context)
        
        # Generate human-readable response
        formatted = _format_analysis_for_log(result)
        
        response_data = {
            "intent": parsed.intent,
            "entities": parsed.entities,
            "result": result,
            "formatted_output": formatted
        }
        
        # Store in history
        dashboard_state.query_history.append({
            "query": request.query,
            "parsed": parsed.__dict__ if hasattr(parsed, '__dict__') else str(parsed),
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 50
        if len(dashboard_state.query_history) > 50:
            dashboard_state.query_history = dashboard_state.query_history[-50:]
        
        dashboard_state.latest_results = response_data
        
        return NLQueryResponse(**response_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/external_agent_query")
async def process_external_agent_query(request: ExternalAgentQueryRequest):
    """
    Endpoint for external agents to submit queries and receive results.
    This is a conceptual endpoint for the 'Open Ecosystem' phase.
    """
    try:
        # In a real system, this would involve:
        # 1. Authentication and Authorization of agent_id
        # 2. Rate limiting and resource management
        # 3. More sophisticated context handling for external agents

        logger.info(f"External agent '{request.agent_id}' submitted query: '{request.query}'")

        # Route through orchestrator, potentially with a special flag for external agents
        result = await coordinator.route_query(request.query, context={"external_agent_id": request.agent_id, **(request.context or {})})

        # Generate human-readable response (optional for external agents, they might prefer raw JSON)
        formatted = _format_analysis_for_log(result)

        response_data = {
            "status": "success",
            "query_id": result.get("query_id"), # Assuming orchestrator adds query_id
            "result": result,
            "formatted_output": formatted,
            "message": f"Query processed for external agent '{request.agent_id}'."
        }

        # External agents might poll for results or receive via a dedicated webhook
        # For now, we return the result directly.
        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"Error processing external agent query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trade_roadmap")
async def get_trade_roadmap():
    """Get the latest full trade roadmap analysis."""
    # The latest result is stored in dashboard_state after a query
    latest_result = dashboard_state.latest_results.get("result", {})
    if latest_result and "scalping" in latest_result:
        return latest_result

    # As a fallback, check memory directly
    latest_multistyle = global_memory.get(f"multistyle:{dashboard_state.current_symbol}")
    if latest_multistyle:
        return latest_multistyle

    raise HTTPException(status_code=404, detail="No trade roadmap has been generated yet. Run an analysis query first.")
# ============ Dashboard Bridge Endpoints ============

class AgentUpdate(BaseModel):
    name: str
    status: str
    tokens_used: int
    tasks_completed: int
    avg_response_time: float
    success_rate: float
    current_task: Optional[str] = None

@app.post("/agent/update")
async def update_agent_status(update: AgentUpdate):
    """Receive agent status updates from the dashboard bridge."""
    dashboard_state.agent_states[update.name] = update.dict()
    global_memory.store(f"agent:{update.name}:status", update.status)
    return {"success": True}

class TaskEvent(BaseModel):
    agent: str
    task: str
    status: str
    timestamp: str
    duration: Optional[float] = None

@app.post("/task/event")
async def log_task_event(event: TaskEvent):
    """Log task events from agents."""
    return {"success": True}

@app.get("/metrics")
async def get_system_metrics():
    """Current system metrics for the dashboard bridge."""
    return {
        "status": "online",
        "active_agents": len(dashboard_state.agent_states),
        "queries_processed": len(dashboard_state.query_history)
    }


@app.get("/api/agents/capabilities")
async def get_agent_capabilities():
    """Get capabilities of all registered agents."""
    capabilities = {}
    for name, agent in coordinator._agents.items():
        if hasattr(agent, 'get_capability'):
            capabilities[name] = agent.get_capability()
        else:
            capabilities[name] = {
                "name": name,
                "description": "Agent",
                "supported_operations": [],
                "dependencies": []
            }
    return capabilities


@app.get("/api/agents/status")
async def get_agent_status():
    """Get current status of all agents."""
    return coordinator.get_agent_status()


@app.post("/api/agents/{agent_name}/execute")
async def execute_agent(agent_name: str, parameters: Dict):
    """Execute a specific agent directly."""
    if agent_name not in coordinator._agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
    
    agent = coordinator._agents[agent_name]
    context = coordinator._gather_context(agent_name, [agent_name], {})
    
    try:
        if asyncio.iscoroutinefunction(agent.execute):
            result = await agent.execute(parameters, context)
        else:
            result = agent.execute(parameters, context)
        return {"agent": agent_name, "result": result, "success": True}
    except Exception as e:
        return {"agent": agent_name, "error": str(e), "success": False}


@app.post("/api/visualization/market_data")
async def get_market_visualization(request: VisualizationDataRequest):
    """Get market data formatted for visualization."""
    try:
        # Ensure symbol is formatted correctly (e.g., BTC/USDT)
        symbol = request.symbol.replace('_', '/').upper()
        timeframe = request.timeframe.lower()
        ohlcv = None
        
        # 1. Try crypto exchanges via CCXT
        if '/' in symbol:
            # Use the global, pre-initialized exchange pool for efficiency and rate-limit safety
            for exchange_id in ['binance', 'kraken', 'kucoin']: # Define order of preference
                exchange = exchange_pool.get(exchange_id)
                if not exchange:
                    continue
                
                # Check if the exchange supports the symbol
                if exchange.markets and symbol in exchange.markets:
                    try:
                        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
                        if ohlcv:
                            break # Found data, exit loop
                    except Exception as e:
                        logger.debug(f"Failed to fetch from {exchange.id} (falling back): {type(e).__name__}: {e}")
        
        # 2. Fallback to yfinance (handles stocks like AAPL and crypto via Yahoo Finance)
        if not ohlcv:
            try:
                import yfinance as yf
                yf_symbol = symbol.replace('/', '-')
                if yf_symbol.endswith('-USDT'):
                    yf_symbol = yf_symbol.replace('-USDT', '-USD')

                yf_interval_map = {
                    "1d": ("100d", "1d"),
                    "4h": ("60d", "1h"),
                    "1h": ("60d", "1h"),
                    "30m": ("60d", "30m"),
                    "15m": ("60d", "15m"),
                    "10m": ("60d", "5m"), # yfinance fallback for 10m
                    "5m": ("60d", "5m"),
                    "1m": ("7d", "1m")
                }
                
                if timeframe in yf_interval_map:
                    yf_period, yf_interval = yf_interval_map[timeframe]
                    ticker = yf.Ticker(yf_symbol)
                    df = ticker.history(period=yf_period, interval=yf_interval)
                    if not df.empty:
                        ohlcv = []
                        df = df.tail(100)
                        for index, row in df.iterrows():
                            ohlcv.append([
                                int(index.timestamp() * 1000),
                                float(row['Open']),
                                float(row['High']),
                                float(row['Low']),
                                float(row['Close']),
                                float(row['Volume'])
                            ])
                else:
                    logger.debug(f"yfinance does not support timeframe '{timeframe}'. Skipping yfinance fallback.")
            except ImportError:
                logger.warning("yfinance not installed, skipping fallback.")
            except Exception as e:
                logger.warning(f"yfinance fetch failed: {e}")
        
        if not ohlcv:
            raise HTTPException(status_code=404, detail="No data available from any source")
        
        import datetime
        import numpy as np
        import pandas as pd
        from agents.quant_agent import TechnicalIndicators
        
        try:
            closes_series = pd.Series([c[4] for c in ohlcv])
            rsi_series = TechnicalIndicators.rsi(closes_series, 14).fillna(50).tolist()
            macd, signal, _ = TechnicalIndicators.macd(closes_series)
            macd = macd.fillna(0).tolist()
            signal = signal.fillna(0).tolist()
        except Exception as e:
            logger.error(f"Indicator calculation error: {e}")
            rsi_series = []
            macd = []
            signal = []

        # --- Generate historical signals for chart markers (demonstration) ---
        # In a real system, this logic would live in the quant agent and be
        # more sophisticated, likely using the selected 'strategy'.
        historical_signals = []
        if rsi_series and len(ohlcv) > 0: # Removed strategy dependency
            try:
                # Simple RSI-based scalping strategy for demonstration
                for i in range(1, len(rsi_series)):
                    # Buy signal: RSI crosses above 35 (oversold exit)
                    if rsi_series[i-1] <= 35 and rsi_series[i] > 35:
                        historical_signals.append({
                            "id": f"buy_{i}",
                            "time": ohlcv[i][0] / 1000,
                            "position": "belowBar",
                            "color": "#22c55e",
                            "shape": "arrowUp",
                            "text": "Scalp Buy"
                        })
                    # Sell signal: RSI crosses below 65 (overbought exit)
                    elif rsi_series[i-1] >= 65 and rsi_series[i] < 65:
                        historical_signals.append({
                            "id": f"sell_{i}",
                            "time": ohlcv[i][0] / 1000,
                            "position": "aboveBar",
                            "color": "#ef4444",
                            "shape": "arrowDown",
                            "text": "Scalp Sell"
                        })
            except Exception as e:
                logger.warning(f"Could not generate historical signals: {e}")

        data = {
            "timestamps": [datetime.datetime.fromtimestamp(c[0]/1000).isoformat() for c in ohlcv],
            "opens": [c[1] for c in ohlcv],
            "highs": [c[2] for c in ohlcv],
            "lows": [c[3] for c in ohlcv],
            "closes": [c[4] for c in ohlcv],
            "volumes": [c[5] for c in ohlcv],
            "rsi_14": rsi_series,
            "macd": macd,
            "signal": signal,
            "historical_signals": historical_signals
        }
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market/orderbook")
async def get_order_book(symbol: str, limit: int = 10):
    """Get L2 order book data."""
    if not exchange_pool:
        raise HTTPException(status_code=503, detail="Exchange services are currently unavailable due to connection issues.")

    try:
        symbol = symbol.replace('_', '/').upper()
        order_book = None
        if '/' in symbol:
            # Use the global, pre-initialized exchange pool for efficiency and rate-limit safety
            for exchange_id in ['binance', 'kraken', 'kucoin']: # Define order of preference
                exchange = exchange_pool.get(exchange_id)
                if not exchange:
                    continue
                
                # Check if the exchange supports the symbol
                if exchange.markets and symbol in exchange.markets:
                    try:
                        # fetchL2OrderBook is often more efficient
                        order_book = await exchange.fetch_l2_order_book(symbol, limit=limit)
                        if order_book:
                            break # Found data, exit loop
                    except Exception as e:
                        logger.debug(f"Failed to fetch order book from {exchange.id} (falling back): {type(e).__name__}: {e}")
                        continue # Try next exchange
        
        if not order_book:
            raise HTTPException(status_code=404, detail=f"Order book not available for {symbol} on supported exchanges.")

        return {"bids": order_book['bids'], "asks": order_book['asks'], "timestamp": order_book['timestamp']}
    except HTTPException:
        raise  # Re-raise HTTPException directly to avoid being caught by the generic exception handler
    except Exception as e:
        logger.error(f"Error fetching order book for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/visualization/indicators")
async def get_indicators(symbol: str, timeframe: str = "1d"):
    """Get calculated indicators for charting."""
    result = global_memory.get(f"quant:{symbol}")
    if result and "analysis" in result:
        indicators = result["analysis"].get("indicators", {})
        return indicators
    return {}


@app.get("/api/visualization/sentiment")
async def get_sentiment(symbol: str):
    """Get sentiment data for gauge visualization."""
    result = global_memory.get(f"research:{symbol}")
    if result and "research" in result:
        sentiment = result["research"].get("overall_sentiment", "Neutral")
        fgi = result["research"].get("macro_sentiment", {})
        return {
            "classification": sentiment,
            "score": fgi.get("sentiment_score", 0),
            "fear_greed": fgi.get("fear_greed_index", 50)
        }
    return {"classification": "Neutral", "score": 0, "fear_greed": 50}


@app.get("/api/visualization/risk")
async def get_risk_metrics(symbol: str):
    """Get risk metrics for visualization."""
    result = global_memory.get(f"risk:{symbol}")
    if result and "risk_assessment" in result:
        risk = result["risk_assessment"]
        return {
            "var": risk.get("var", {}).get("var", 0),
            "max_drawdown": risk.get("stress_tests", {}).get("worst_case", {}).get("impact_pct", 0),
            "risk_level": risk.get("risk_level", "MEDIUM"),
            "sl": risk.get("trade_limits", {}).get("stop_loss", 0),
            "tp": risk.get("trade_limits", {}).get("take_profit", 0)
        }
    return {}


@app.get("/api/history")
async def get_query_history(limit: int = 20):
    """Get recent query history."""
    return {"history": dashboard_state.query_history[-limit:]}


@app.get("/api/trades")
async def get_trade_history(limit: int = 7):
    """Get recent trade history from paper log."""
    file_path = "paper_trades_log.json"
    if not os.path.exists(file_path):
        return {"trades": []}
    try:
        with open(file_path, "r") as f:
            trades = json.load(f)
        # Return last `limit` trades, most recent first
        return {"trades": sorted(trades, key=lambda x: x.get('timestamp', ''), reverse=True)[:limit]}
    except Exception as e:
        logger.error(f"Error reading trade log: {e}")
        # Return empty list on error to prevent dashboard crash
        return {"trades": [], "error": str(e)}


@app.get("/api/portfolio")
async def get_portfolio():
    """Get current virtual portfolio state."""
    file_path = "portfolio.json"
    if not os.path.exists(file_path):
        return {"cash": 100000.0, "assets": {}}
    try:
        with open(file_path, "r") as f:
            portfolio = json.load(f)
        return portfolio
    except Exception as e:
        logger.error(f"Error reading portfolio: {e}")
        return {"cash": 100000.0, "assets": {}, "error": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Receive any client messages
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "subscribe":
                # Handle subscription requests
                pass
            
            if message.get("type") == "set_symbol":
                new_symbol = message.get("symbol")
                if new_symbol and isinstance(new_symbol, str):
                    # Unsubscribe from old symbol's tick channel and subscribe to new one if needed
                    # (Future implementation for tick-by-tick data)
                    
                    # Update dashboard state
                    dashboard_state.current_symbol = new_symbol
                    logger.info(f"Dashboard symbol changed to {new_symbol} via WebSocket.")

                    # Automatically trigger analysis for the new symbol
                    logger.info(f"Automatically triggering analysis for new symbol: {new_symbol}")
                    
                    # Create a background task to not block the websocket
                    async def run_analysis_for_symbol(symbol_to_analyze: str):
                        try:
                            query = f"Analyze {symbol_to_analyze} and execute paper trades"
                            query_context = {}
                            
                            # Re-use logic from the /api/query endpoint to get live price
                            if exchange_for_ticker:
                                try:
                                    logger.debug(f"Fetching live price for {symbol_to_analyze} on-demand...")
                                    ticker = await exchange_for_ticker.fetch_ticker(symbol_to_analyze)
                                    live_price = ticker.get('last')
                                    if live_price is not None:
                                        query_context['live_price'] = live_price
                                        logger.debug(f"Live price {live_price} for {symbol_to_analyze} added to context.")
                                except Exception as e:
                                    logger.warning(f"On-demand live price fetch for {symbol_to_analyze} failed: {e}")

                            result = await coordinator.route_query(query, context=query_context)
                            formatted = _format_analysis_for_log(result)
                            
                            response_data = {
                                "intent": "analyze",
                                "entities": {"symbol": symbol_to_analyze},
                                "result": result,
                                "formatted_output": formatted
                            }
                            
                            # Update dashboard state with the new results
                            dashboard_state.latest_results = response_data
                            
                            # Add to query history so the frontend detects a new query count
                            dashboard_state.query_history.append({
                                "query": query,
                                "timestamp": datetime.now().isoformat()
                            })
                            
                            logger.info(f"Analysis for {symbol_to_analyze} complete. Results are available for broadcast.")
                        except Exception as e:
                            logger.error(f"Error in background analysis for {symbol_to_analyze}: {e}")
                            # Send an error result so the UI doesn't hang forever
                            dashboard_state.latest_results = {
                                "intent": "analyze",
                                "entities": {"symbol": symbol_to_analyze},
                                "result": {"error": str(e), "summary": {"market_bias": "Error analyzing asset"}},
                                "formatted_output": f"Analysis failed: {e}"
                            }
                            dashboard_state.query_history.append({"query": f"Analyze {symbol_to_analyze}", "timestamp": datetime.now().isoformat()})

                    asyncio.create_task(run_analysis_for_symbol(new_symbol))

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Start dashboard server function
def run_dashboard(host: str = "0.0.0.0", port: int = 8000):
    """Run the dashboard server."""
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())


if __name__ == "__main__":
    run_dashboard()