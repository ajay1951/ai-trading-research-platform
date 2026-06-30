# AI Agent Dashboard

Real-time web-based monitoring interface for the multi-agent AI trading system.

## Features

- **Agent Status Grid**: Real-time status of all 7 agents with task counts and token usage
- **Performance Charts**: Live line charts for response times, pie charts for workload distribution
- **Resource Heatmap**: Visual representation of token usage across agents
- **Task Logs**: Live streaming of task events with timestamps
- **System Health**: Overall system metrics and health indicators

## Running the Dashboard

```bash
# Terminal 1: Start the dashboard server
cd dashboard
python dashboard_server.py

# Terminal 2: Run the trading bot (connects automatically)
python main.py
```

Then open http://localhost:8000 in your browser.

## API Endpoints

- `GET /` - Dashboard UI
- `GET /ws` - WebSocket for real-time updates
- `POST /agent/update` - Update agent metrics
- `POST /task/event` - Log task events
- `GET /metrics` - Current system metrics

## Integration

The dashboard integrates via `dashboard_bridge.py`:

```python
from dashboard.dashboard_bridge import dashboard

# Update agent status
dashboard.update_agent("Data Engineer", "active", 1500)

# Log task events
dashboard.log_task("Quant", "strategy_task", "completed", 2.5)
```

## Architecture

```
main.py ──► DashboardBridge ──► WebSocket Server ──► Browser UI
                              (dashboard_server.py)
```