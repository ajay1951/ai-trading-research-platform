# System Flow & Architecture

## Autonomous Scanning Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│  USER INPUT                                                          │
│  "Analyze BTC/USDT and tell me if I should buy"                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NATURAL LANGUAGE INTERFACE                                          │
│  ├─ Parse query: intent="analyze"                                   │
│  ├─ Extract entities: symbol="BTC/USDT", metrics=["price","signal"] │
│  └─ Classify action: analyze → route to all agents                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MASTER COORDINATOR (Dual-Lane Async)                                │
│  ├─ Fast Lane (Foreground): [data, quant, risk]                     │
│  ├─ Slow Lane (Background): [research, supervisor]                  │
│  └─ Executes math deterministically while offloading LLMs           │
└──────────────┬───────────────┬───────────────┬───────────────────────┘
               │               │               │
               ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐   ┌──────────┐
        │ Data     │    │ Research │   │   Quant  │
        │ Agent    │    │  Agent   │   │  Agent   │
        ├──────────┤    ├──────────┤   ├──────────┤
        │ • Fetch  │    │ • News   │   │ • RSI    │
        │   market │    │ • Sentiment│ │ • MACD   │
        │ • SEC    │    │ • Macro  │   │ • Signal │
        │   filings│    │   summary│   │ • Backtest│
        └─────┬────┘    └─────┬────┘   └─────┬────┘
              │               │               │
              └───────┬───────┴───────────────┘
                      │
                      ▼
        ┌─────────────────────────────────┐
        │  Shared Memory (Pub/Sub)        │
        │  data:BTC/USDT → stored         │
        │  research:BTC → stored          │
        │  quant:BTC → stored             │
        │  All agents can read each       │
        │  other's outputs                │
        └────────────┬────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────────┐
        │  Risk Agent (reads quant data)  │
        │  ├─ Calculate VaR               │
        │  ├─ Run stress tests            │
        │  ├─ Compute SL/TP               │
        │  └─ Output: risk_assessment     │
        └────────────┬────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────────┐
        │  Supervisor Agent (final check) │
        │  ├─ Review all outputs          │
        │  ├─ Check for conflicts         │
        │  └─ Request re-analysis if needed│
        └────────────┬────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────────┐
        │  FINAL CONSOLIDATED RESULT       │
        │  ├─ Trading Signal: BUY/SELL/HOLD│
        │  ├─ Confidence: 85%              │
        │  ├─ TP/SL levels                 │
        │  ├─ Risk metrics (VaR, DD)       │
        │  ├─ Sentiment (Bullish/Neutral)  │
        │  └─ Detailed agent reports       │
        └────────────┬────────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
    ┌────────┐ ┌────────┐ ┌────────┐
    │ WEB    │ │ TERM-  │ │ CON-   │
    │ DASH-  │ │ INAL   │ │ SOLE   │
    │ BOARD  │ │  UI    │ │  CLI   │
    ├────────┤ ├────────┤ ├────────┤
    │ Chart.js│ │ Rich   │ │ Text   │
    │ WS     │ │ TUI    │ │ Output │
    │graphs  │ │Live    │ │        │
    └────────┘ └────────┘ └────────┘
```

## Data Flow Architecture

```
┌─────────────────┐
│  External APIs  │
│  • Binance CCXT  │
│  • DuckDuckGo   │
│  • SEC EDGAR    │
│  • Fear & Greed │
└────────┬────────┘
         │
         ▼
┌───────────────────────────────────────────┐
│  WebSocketMarketStream (Daemon)           │
│  1. CCXT.pro async continuous stream      │
│  2. Direct injection to SharedMemory      │
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│  QuantitativeAnalysisAgent (Fast Lane)    │
│  1. Read live tick data from memory       │
│  2. Stat Arb Z-Score Spread Calculation   │
│  3. Generate Pairs Signal (SHORT A/LONG B)│
│  4. Store: quant:BTC/USDT                 │
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│  FundamentalResearchAgent                 │
│  1. Read news data                        │
│  2. Sentiment analysis (keyword lexicon)  │
│  3. Macro aggregation                     │
│  4. Store: research:BTC/USDT              │
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│  RiskManagementAgent (Fast Lane)          │
│  1. Read quant signal + indicators        │
│  2. Dynamic ATR Position Sizing           │
│  3. Compute Dynamic ATR-based SL/TP       │
│  4. Output instantly to Fast Lane         │
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│  Supervisor Agent                         │
│  1. Read all agent outputs                │
│  2. Check for signal conflicts            │
│  3. Validate risk limits                  │
│  4. Request re-analysis if needed         │
│  5. Final consolidation                   │
└───────────┬───────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│  OUTPUT INTERFACES                         │
│  ├─ Web Dashboard (FastAPI)               │
│  │  └─ WebSocket → Chart.js updates       │
│  ├─ Terminal UI (Rich)                    │
│  │  └─ Live panel refreshing              │
│  └─ CLI console                           │
│     └─ Formatted text report              │
└───────────────────────────────────────────┘
```

## Agent Dependency Graph

```
    data_agent (no deps)
         │
         ├──> quant_agent (depends on data)
         │        │
         │        └──> risk_agent (depends on quant, data)
         │
         └──> research_agent (depends on data)
                  │
                  └──> (feeds into supervisor)
```

Execution order is automatically resolved by topological sort.

## Storage Backend routing

```
        ┌──────────────────┐
        │   Application    │
        │   Code           │
        └────────┬─────────┘
                 │
                 ▼
        ┌──────────────────┐
        │   SharedMemory   │
        │   (Singleton)    │
        │                  │
        │  _storage: In-   │
        │    MemoryStorage │
        └────────┬─────────┘
                 │
         ┌───────┼───────┐
         │       │       │
         ▼       ▼       ▼
    ┌────────┐ ┌───────┐ ┌──────────┐
    │ Redis  │ │Chroma │ │ InfluxDB │
    │ Pub/Sub│ │Vector │ │Time-Series│
    │Cache   │ │Search │ │Storage   │
    └────────┘ └───────┘ └──────────┘
```

## Technology Stack Integration

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   CrewAI     │  │  FastAPI     │  │   Rich TUI   │    │
│  │   Agents     │  │  Dashboard   │  │  Dashboard   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                    ORCHESTRATION LAYER                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MasterCoordinator (async routing, dependencies)     │  │
│  │  NaturalLanguageInterface (parsing, generation)     │  │
│  └──────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    DATA & MEMORY LAYER                      │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐     │
│  │  Redis      │  │  ChromaDB   │  │  InfluxDB    │     │
│  │  (pub/sub)  │  │  (vectors)  │  │  (timeseries)│     │
│  └─────────────┘  └─────────────┘  └──────────────┘     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         SharedMemory (Singleton Gateway)            │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    EXTERNAL APIS & DATA                     │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌────────────┐ │
│  │ Binance  │ │ Duck-    │ │  SEC       │ │ Fear &     │ │
│  │ CCXT     │ │ DuckGo   │ │  EDGAR     │ │ Greed      │ │
│  └──────────┘ └──────────┘ └────────────┘ └────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Concurrency Model

```
┌──────────────────────────────────────────────────────────┐
│              Main Thread (FastAPI)                        │
│  ├─ API request handlers                                 │
│  ├─ WebSocket connections                                │
│  └─ Spawns agent threads as needed                       │
├──────────────────────────────────────────────────────────┤
│              Agent Worker Threads                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │ Data    │  │ Quant   │  │ Research│  │ Risk    │    │
│  │ Thread  │  │ Thread  │  │ Thread  │  │ Thread  │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │
├──────────────────────────────────────────────────────────┤
│              Terminal UI Thread                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Rich Live Rendering (refresh 2-4 FPS)           │    │
│  │  Reads from SharedMemory (thread-safe)           │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘

Locking: SharedMemory uses RLock for concurrent access
No race conditions - all state updates atomic
```

## File Dependency Graph

```
main.py
├── core/
│   ├── memory.py         ← (base singleton)
│   ├── orchestrator.py   ← uses memory
│   ├── nl_interface.py   ← independent
│   └── storage.py        ← independent
├── agents/
│   ├── data_agent.py     ← uses memory, tools
│   ├── quant_agent.py    ← uses memory, models
│   ├── research_agent.py ← uses memory
│   └── risk_agent.py     ← uses memory, models
├── models/
│   ├── technical_indicators.py  ← numpy/pandas only
│   └── risk_models.py           ← numpy/scipy only
├── tools/
│   ├── market_tools.py   ← uses CCXT
│   ├── news_tools.py     ← uses DuckDuckGo
│   └── execution_tools.py← pure Python
└── dashboard/
    └── dashboard_server.py ← uses FastAPI, memory
```

## Startup Sequence

1. **Import Phase** (module load)
   - Load config (OpenRouter API key)
   - Initialize singletons (memory, coordinator, nl_interface)
   - Create tools (fetch_data, fetch_news, fetch_sec)

2. **System Init** (FinancialIntelligenceSystem.__init__)
   - Connect storage backends (Redis/Chroma/Influx if enabled)
   - Register agents with coordinator
   - Initialize agent instances

3. **Service Startup** (main())
   - Start dashboard thread (if enabled)
   - Start TUI thread (if enabled)
   - Wait for user input

4. **Query Execution** (system.analyze())
   - Parse NL query → ParsedQuery
   - Coordinator detects intent & resolves dependencies
   - Execute agents sequentially (respecting dependencies)
   - Each agent reads from memory, writes result
   - Supervisor reviews & consolidates
   - Update TUI/dashboard with results
   - Return structured result

5. **Display** (formatted output)
   - NL interface generates human-readable report
   - TUI updates panels in real-time
   - Dashboard pushes WebSocket messages
   - CLI prints to console

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Market data fetch | <0.01s | CCXT.pro WebSocket Stream |
| Technical analysis | <0.05s | Pure Python/Pandas Vectorized |
| Risk & Sizing | <0.05s | Pure Math |
| LLM inference | 2-5s | Slow Lane Background (OpenRouter) |
| Order Execution | <0.1s | Authenticated CCXT.pro WebSocket |

Total Fast Lane Math Execution: ~0.1 seconds (Instantaneous)

## Scaling Considerations

**Horizontal scaling:**
- Each agent could run as separate microservice
- Coordinator becomes API gateway
- Redis pub/sub for inter-agent communication
- Shared DB for state persistence

**Vertical scaling:**
- Multiple concurrent queries via asyncio.gather
- Agent pooling (create N instances of each type)
- Redis caching for market data (deduplicate)

**Production deployment:**
- Kubernetes deployment per agent
- Load balancer for coordinator
- Persistent Redis/Chroma/InfluxDB clusters
- Prometheus metrics collection
- Circuit breakers for external APIs
