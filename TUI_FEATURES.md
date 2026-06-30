# Terminal UI (TUI) Features - Bloomberg Terminal Edition

## Overview

The Terminal UI provides a full-screen, real-time dashboard inspired by Bloomberg Terminal aesthetics. Built with the `rich` library, it delivers professional-grade financial data visualization directly in your terminal.

## Visual Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ 📈 FINANCIAL AI – Bloomberg Terminal Edition                   │
│ SYMBOL: BTC/USDT                                   ● ONLINE     │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│ │ MARKET DATA │ │   SIGNAL    │ │  SENTIMENT  │                │
│ │             │ │             │ │             │                │
│ │ PRICE  $... │ │ BUY         │ │ Bullish     │                │
│ │ 24H Δ +2.5% │ │ [██████░░]  │ │ F&G [████░░]│                │
│ │ HIGH ...    │ │ 80%         │ │ 75/100      │                │
│ │ LOW ...     │ │ TP $...     │ │             │                │
│ │ VOL ...     │ │ SL $...     │ │             │                │
│ │ TREND ─┐    │ │             │ │             │                │
│ └─────────────┘ └─────────────┘ └─────────────┘                │
│ ┌─────────────────────┐ ┌─────────────────────────────────┐     │
│ │   AGENT STATUS      │ │         ACTIVITY LOG            │     │
│ │ Engineer  ▶️  5     │ │ 14:23:01 Quant   calc signal   │     │
│ │ Researcher 💤  3    │ │ 14:22:58 Data    fetch market  │     │
│ │ Quant      💤  8    │ │ 14:22:55 System Analysis start │     │
│ │ Portfolio  💤  2    │ │ ...                            │     │
│ │ Risk CRO   💤  4    │ │                                │     │
│ │ HFT        💤  1    │ │                                │     │
│ │ Supervisor 💤  6    │ │                                │     │
│ └─────────────────────┘ └─────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
 Hotkeys: [Q]uit [C]lear [/]Command        ● READY   14:23:45
```

## Panel Details

### 1. Market Data Panel (Top-Left)

Displays real-time price information with ASCII sparkline trend.

**Fields:**
- `PRICE` - Current last price with color (green/red)
- `24H Δ` - 24-hour change percentage
- `HIGH` - 24h high
- `LOW` - 24h low
- `VOLUME` - Trading volume
- `TREND` - ASCII sparkline showing price movement

**Example:**
```
PRICE  $67,432.50
24H Δ  +2.45%
HIGH   $68,120.00
LOW    $65,890.00
VOLUME  1.2B
TREND  ─┐    █▆▄█
```

### 2. Trading Signal Panel (Top-Center)

Shows the current trading recommendation with confidence visualization.

**Fields:**
- `SIGNAL` - BUY / SELL / HOLD (color-coded: green/red/yellow)
- `CONFIDENCE` - Horizontal bar showing strength (0-100%)
- `STRENGTH` - Numeric percentage
- `REASON` - Top reason for signal (e.g., "RSI oversold")
- `TP` - Take-Profit price level
- `SL` - Stop-Loss price level

**Confidence Bar:**
```
[████████░░░░░░] 80%
█ = filled based on strength
░ = remaining
```

### 3. Sentiment Panel (Top-Right)

Market sentiment visualization with Fear & Greed gauge.

**Fields:**
- `SENTIMENT` - Bullish / Bearish / Neutral
- `F&G INDEX` - ASCII gauge bar (0-100)
- `VALUE` - Numeric fear/greed score

**Color Coding:**
- 0-30: Extreme Fear → RED
- 30-70: Neutral → YELLOW
- 70-100: Extreme Greed → GREEN

### 4. Agent Status Grid (Bottom-Left)

7x3 table showing all agents with emoji status indicators.

**Columns:**
- `AGENT` - Agent name
- `STATUS` - Current state with emoji:
  - ▶️ active (green) - currently processing
  - 🔄 busy (cyan) - working on task
  - 💤 idle (yellow) - waiting
  - ❌ error (red) - failed
- `TASKS` - Count of completed tasks
- `LAST ACTIVE` - Timestamp of last activity

### 5. Activity Log (Bottom-Right)

Rolling log of recent system events.

**Columns:**
- `TIME` - HH:MM:SS
- `AGENT` - Agent name (truncated to 12 chars)
- `TASK` - Brief task description
- `STATUS` - completed/failed/warning (color-coded)

Shows last 12 entries by default.

### 6. Footer

System status bar with hotkeys and timestamp.

**Left:** Hotkey reference
**Center:** System status (● READY / ● PROCESSING)
**Right:** Last update timestamp

## Color Scheme

| Element | Color | Usage |
|---------|-------|-------|
| Background | `#0a0a0a` | Pure black |
| Panel Background | `#1a1a2e` | Dark blue-black |
| Border | `#16213e` | Navy blue |
| Accent | `#00d4ff` | Cyan (highlights) |
| Success / Bullish | `#00ff88` | Green |
| Warning / Neutral | `#ffaa00` | Orange/Yellow |
| Danger / Bearish | `#ff4444` | Red |
| Text | `#e0e0e0` | Off-white |

## Interactive Features

### Real-Time Updates

The TUI refreshes every 1 second automatically, pulling data from:
- Shared memory (agent states)
- Latest analysis results
- Market data cache

### Hotkeys

| Key | Action |
|-----|--------|
| `Q` | Quit application |
| `C` | Clear screen (redraw) |
| `/` | Enter command mode (same as CLI) |

### Commands

Type `/` followed by command in the activity log area (or use CLI mode):

```
/symbol BTC/USDT     - Change the tracked cryptocurrency
/agents              - List all registered agents and capabilities
/memory              - Show all keys in shared memory
/clear               - Clear agent memory
/help                - Show help
```

## Sparkline Generation

ASCII sparklines use Unicode block characters for smooth curves:

```
▁▂▃▄▅▆▇█
```

The trend line in the Market Data panel shows the last 50 price points, normalized to fit in 25 characters. Green sparkline = uptrend, Red = downtrend.

## Integration with Backend

The TUI connects to the same backend as the web dashboard:

1. **Initialization:** `terminal_dashboard = TerminalDashboard()`
2. **Updates:** Agents call `terminal_dashboard.update_agent()` etc.
3. **Live Rendering:** `rich.Live` context manager handles screen refresh
4. **Thread Safety:** All state updates use `threading.Lock`

## Requirements

```txt
rich>=13.0.0
textual>=1.0.0
```

## Performance

- Memory footprint: ~50MB
- CPU usage: <2% (idle), ~5% (updating)
- Refresh rate: 2-4 FPS (configurable)
- Terminal size: Minimum 80x24 recommended, 120x40 optimal

## Known Limitations

- Windows CMD may not render Unicode emoji correctly (use Windows Terminal)
- Some color schemes may vary by terminal emulator
- Very small terminals (<80 columns) will truncate panels
- SSH connections work but latency may affect smoothness

## Customization

Edit `terminal_ui.py` to customize:

```python
# Colors
COLORS = {
    'bg': '#0a0a0a',
    'accent': '#00d4ff',
    ...
}

# Update interval (seconds)
update_interval = 1.0

# Panel sizes
Layout(header, size=3)  # Change header height
```

## Screenshot Examples

### Stock Analysis Mode
```
SYMBOL: AAPL
Signal: HOLD (confidence 65%)
RSI: 52.3, MACD: bullish crossover
Sentiment: Neutral (F&G: 55)
```

### Crypto Bull Market
```
SYMBOL: BTC/USDT
Signal: BUY (confidence 85%)
Price: $72,450 (+5.2%)
Sentiment: Bullish (F&G: 82)
```

### Risk-Off Mode
```
SYMBOL: ETH/USDT
Signal: SELL (confidence 70%)
VaR: -4.2%
Stress: -18%
Recommendation: HOLD (high risk)
```
