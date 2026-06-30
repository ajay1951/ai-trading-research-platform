"""
AUTONOMOUS TRADING AI - TERMINAL INTERFACE
Provides a real-time, "Bloomberg Terminal" style view of the autonomous
market scanning engine's output.
"""
import asyncio
import threading
import time
import json
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.progress import BarColumn, Progress
from rich import box
from rich.rule import Rule
from rich.style import Style
from rich.syntax import Syntax
from core.orchestrator import coordinator


class AutonomousScanner:
    """
    Encapsulates the logic for the autonomous market scanning loop.
    """
    CORE_ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]

    def __init__(self, memory, console):
        self.memory = memory
        self.console = console
        self.is_scanning = False

    async def run_scan_cycle(self):
        """Runs a single, full scan cycle of all assets."""
        if self.is_scanning:
            return
        self.is_scanning = True
        self.memory.store("autonomous_scan_status", "scanning")
        self.console.log("[bold cyan]Starting new autonomous scan cycle...[/bold cyan]")

        try:
            # 1. Get assets to scan
            trending_assets_tool = coordinator._agents['data'].tools.get('trending')
            trending_assets_str = await trending_assets_tool._run()
            trending_assets = json.loads(trending_assets_str)
            
            scan_symbols = set(self.CORE_ASSETS)
            if "error" not in trending_assets:
                for asset in trending_assets:
                    scan_symbols.add(asset['symbol'])
            
            self.console.log(f"Scan list: {', '.join(list(scan_symbols)[:8])}...")

            # 2. Run analysis for each symbol
            all_results = []
            for symbol in scan_symbols:
                self.console.log(f"Analyzing {symbol}...")
                try:
                    # Use the orchestrator to run the full analysis pipeline which now generates a multi-style roadmap
                    result = await coordinator.route_query(f"Analyze {symbol}")
                    # The result from the supervisor is the full roadmap. We append it if it's valid.
                    if result and result.get("rankings"):
                        all_results.append(result)
                except Exception as e:
                    self.console.log(f"[red]Error analyzing {symbol}: {e}[/red]")

            # 4. Format for display
            final_output = self.format_results(all_results)
            
            # 5. Store in memory for the UI to pick up
            self.memory.store("autonomous_scan_results", final_output)
            self.memory.publish("autonomous_scan_update", final_output)

        except Exception as e:
            self.console.log(f"[bold red]Autonomous scan cycle failed: {e}[/bold red]")
        finally:
            self.is_scanning = False
            self.memory.store("autonomous_scan_status", "idle")
            self.console.log("[bold green]Scan cycle complete.[/bold green]")

    def format_results(self, analysis_results: List[Dict]) -> Dict:
        """Formats the raw analysis from multiple symbols into the final output structure for the TUI."""
        all_ranked_setups = []
        
        # analysis_results is a list of full roadmap objects, one for each symbol
        for result in analysis_results:
            rankings = result.get("rankings", {})
            symbol = result.get("symbol")
            # Use the highest confidence setup for the TUI's main view
            if rankings.get("highest_confidence_setup"):
                setup = rankings["highest_confidence_setup"]
                if 'symbol' not in setup:
                    setup['symbol'] = symbol
                all_ranked_setups.append(setup)

        # Sort all collected "highest confidence" setups by confidence score
        ranked_setups = sorted(all_ranked_setups, key=lambda x: x.get('confidence_score', 0), reverse=True)

        formatted_setups = []
        for i, setup in enumerate(ranked_setups[:4]):  # Take top 4 overall
            # The setup structure from the ranking engine is mostly what we need.
            formatted_setups.append({
                "rank": i + 1,
                "symbol": setup.get('symbol', 'N/A'),
                "signal": setup.get('direction', 'N/A'),
                "confidence": setup.get('confidence_score', 0) * 100,
                "entry": setup.get('entry', 0),
                "stop_loss": setup.get('stop_loss', 0),
                "take_profit": setup.get('tp1', 0),  # Show TP1 as the main target
                "risk_reward": float(str(setup.get('risk_reward_ratio', '0:1')).split(':')[0]),
                # Add dummy data for other fields the old UI might need
                "market_regime": {"trend": setup.get('style', 'N/A'), "phase": "N/A"},
                "smc_analysis": {"liquidity_status": "N/A"},
                "risk_analysis": {"summary": "N/A", "level": setup.get('risk_level', 'N/A')},
                "final_verdict": setup.get('reasoning', 'No verdict.')
            })

        # Placeholder summaries for the bottom panels
        market_summary = {"overall_condition": "Mixed, BTC dominant", "volatility_environment": "Contracting", "risk_state": "Risk-Neutral"}
        portfolio_exposure = {"current_exposure": "0% (Flat)", "target_exposure": "Calculated by Portfolio Manager"}
        execution_decision = {"approved": [s['symbol'] for s in formatted_setups], "rejected": []}

        return {
            "timestamp": datetime.now().isoformat(),
            "ranked_setups": formatted_setups,
            "market_summary": market_summary,
            "portfolio_exposure": portfolio_exposure,
            "execution_decision": execution_decision
        }

class TerminalDashboard:
    """
    Autonomous Trading AI Terminal.
    Displays the output of the continuous market scanning engine.
    """
    def __init__(self, scan_interval_minutes: int = 15):
        from core.memory import get_memory
        self.console = Console(force_terminal=True, color_system='truecolor', highlight=False)
        self.scan_interval = scan_interval_minutes * 60
        self.running = False
        self._lock = threading.Lock()
        self.memory = get_memory()
        self.scanner = AutonomousScanner(self.memory, self.console)
        self.scan_results = None
        self.scan_status = "idle"
        self._thread = None
        self._live = None
    
    def start(self):
        """Start the dashboard in a background thread."""
        self.running = True
        self._thread = threading.Thread(target=self._run_dashboard, daemon=True)
        self.memory.subscribe("autonomous_scan_update", self._handle_scan_update)
        self.memory.subscribe("autonomous_scan_status", lambda msg: self.set_scan_status(msg['data']))
        self._thread.start()
        self.console.print("[green]Autonomous Trading Terminal starting...[/green]")
    
    def stop(self):
        """Stop the dashboard."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _handle_scan_update(self, message: Dict):
        """Callback to update the dashboard with new scan results."""
        with self._lock:
            self.scan_results = message['data']

    def set_scan_status(self, status: str):
        with self._lock:
            self.scan_status = status

    def _run_dashboard(self):
        """Run the rich dashboard in a separate thread."""
        try:
            with Live(self._render(), refresh_per_second=2, screen=True, console=self.console) as live:
                self._live = live
                # Initial scan on startup
                asyncio.run(self.scanner.run_scan_cycle())
                
                last_scan_time = time.time()
                while self.running:
                    if time.time() - last_scan_time > self.scan_interval:
                        asyncio.run(self.scanner.run_scan_cycle())
                        last_scan_time = time.time()
                    
                    time.sleep(1) # UI refresh rate
                    live.update(self._render())
        except KeyboardInterrupt:
            pass
        except Exception as e:
            self.console.print(f"[red]Dashboard error: {e}[/red]")
    
    def _render(self) -> Panel:
        """Render the full dashboard."""
        layout = self._build_layout()
        return Panel(layout, border_style="blue", box=box.DOUBLE_EDGE)
    
    def _build_layout(self) -> Layout:
        """Build the nested layout structure."""
        layout = Layout()
        
        # Header
        header = self._render_header()
        layout.split_column(
            Layout(header, size=4),
            Layout(self._render_body(), ratio=1),
            Layout(self._render_footer(), size=3)
        )
        return layout
    
    def _render_header(self) -> Table:
        """Render header bar."""
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(justify="left")
        table.add_column(justify="center")
        table.add_column(justify="right")
        
        title = Text("📈 AUTONOMOUS HEDGE FUND AI SYSTEM", style="bold cyan on #0a0a0a")
        
        status_color = "yellow" if self.scan_status == "scanning" else "green"
        status_text = f"● {self.scan_status.upper()}"
        status = Text(status_text, style=status_color)
        
        last_scan_ts = self.scan_results['timestamp'] if self.scan_results else "N/A"
        
        table.add_row(title, "", f"Last Scan: {datetime.fromisoformat(last_scan_ts).strftime('%H:%M:%S UTC') if last_scan_ts != 'N/A' else 'N/A'}")
        return table
    
    def _render_body(self) -> Layout:
        """Render main body layout."""
        body = Layout()
        
        # Top row: Market | Signal | Sentiment
        bottom_row = Layout(name="bottom")
        bottom_row.split_row(
            self._render_market_summary_panel(),
            self._render_portfolio_exposure_panel(),
            self._render_execution_decision_panel()
        )
        
        body.split_column(
            Layout(self._render_ranked_setups(), name="setups"),
            Layout(bottom_row, size=8, name="summaries")
        )
        return body
    
    def _render_ranked_setups(self) -> Panel:
        """Renders the list of top trade setups."""
        if not self.scan_results or not self.scan_results.get('ranked_setups'):
            return Panel(Text("NO ELITE SETUPS AVAILABLE", justify="center", style="bold dim"), title="[bold]TOP ELITE TRADE SETUPS[/bold]", border_style="yellow")

        layout = Layout()
        setups = self.scan_results['ranked_setups']
        panels = []
        for setup in setups:
            signal_color = "green" if setup['signal'] == "BUY" else "red"
            title = f"[bold]RANK #{setup['rank']}[/bold] | {setup['symbol']} | [bold {signal_color}]{setup['signal']}[/{signal_color}] | CONF: {setup['confidence']:.0f}%"
            
            content_layout = Layout()
            left = Layout(name="left")
            right = Layout(name="right")
            content_layout.split_row(left, right)

            # Left side: Trade details
            trade_table = Table(box=None, show_header=False, expand=True)
            trade_table.add_column(style="cyan", width=12)
            trade_table.add_column()
            trade_table.add_row("ENTRY", f"${setup['entry']:,.2f}")
            trade_table.add_row("STOP LOSS", f"[red]${setup['stop_loss']:,.2f}[/red]")
            trade_table.add_row("TAKE PROFIT", f"[green]${setup['take_profit']:,.2f}[/green]")
            trade_table.add_row("RISK/REWARD", f"1:{setup['risk_reward']:.2f}")
            left.update(trade_table)

            # Right side: Analysis
            analysis_text = Text()
            analysis_text.append("MARKET REGIME:\n", style="bold yellow")
            analysis_text.append(f"  Trend: {setup['market_regime'].get('trend', 'N/A')}\n", style="dim")
            analysis_text.append(f"  Phase: {setup['market_regime'].get('phase', 'N/A')}\n", style="dim")
            analysis_text.append("SMC ANALYSIS:\n", style="bold yellow")
            analysis_text.append(f"  Liquidity: {setup['smc_analysis'].get('liquidity_status', 'N/A')[:50]}...\n", style="dim")
            analysis_text.append("FINAL VERDICT:\n", style="bold yellow")
            analysis_text.append(f"  {setup['final_verdict']}", style="white")
            right.update(analysis_text)

            panels.append(Panel(content_layout, title=title, border_style="blue", height=10))
        
        layout.split_column(*panels)
        return Panel(layout, title="[bold]TOP ELITE TRADE SETUPS[/bold]", border_style="cyan")

    def _render_market_summary_panel(self) -> Panel:
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column(style="cyan", width=15)
        table.add_column()
        summary = (self.scan_results or {}).get('market_summary', {})
        table.add_row("Condition", summary.get('overall_condition', 'N/A'))
        table.add_row("Volatility", summary.get('volatility_environment', 'N/A'))
        table.add_row("Risk State", summary.get('risk_state', 'N/A'))
        return Panel(table, title="[bold]MARKET SUMMARY[/bold]", border_style="magenta")

    def _render_portfolio_exposure_panel(self) -> Panel:
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column(style="cyan", width=15)
        table.add_column()
        exposure = (self.scan_results or {}).get('portfolio_exposure', {})
        table.add_row("Current", exposure.get('current_exposure', 'N/A'))
        table.add_row("Target", exposure.get('target_exposure', 'N/A'))
        return Panel(table, title="[bold]PORTFOLIO EXPOSURE[/bold]", border_style="yellow")

    def _render_execution_decision_panel(self) -> Panel:
        decision = (self.scan_results or {}).get('execution_decision', {})
        approved = decision.get('approved', [])
        
        text = Text()
        text.append("Approved Trades:\n", style="bold green")
        if approved:
            for trade in approved:
                text.append(f"  • {trade}\n", style="white")
        else:
            text.append("  None\n", style="dim")
            
        return Panel(text, title="[bold]FINAL EXECUTION DECISION[/bold]", border_style="green")

    def _render_footer(self) -> Table:
        """Render footer with help & stats."""
        table = Table.grid(expand=True)
        table.add_column(justify="left")
        table.add_column(justify="center")
        table.add_column(justify="right")
        
        # Left: Commands
        commands = Text()
        commands.append("Hotkeys: [Q]uit", style="dim")
        
        # Center: Status
        center = Text()
        status_color = "yellow" if self.scan_status == "scanning" else "green"
        center.append(f"● {self.scan_status.upper()}", style=f"bold {status_color}")
        
        table.add_row(commands, center, f"Scan Interval: {self.scan_interval // 60}m")
        return Panel(table, border_style="dim", box=box.SIMPLE)
    
    def print_banner(self):
        """Print startup banner."""
        banner = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║    █████╗ ██╗   ██╗████████╗ ██████╗ ███╗   ███╗ ██████╗ ███╗   ██╗ ║
║   ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗████╗ ████║██╔═══██╗████╗  ██║ ║
║   ███████║██║   ██║   ██║   ██║   ██║██╔████╔██║██║   ██║██╔██╗ ██║ ║
║   ██╔══██║██║   ██║   ██║   ██║   ██║██║╚██╔╝██║██║   ██║██║╚██╗██║ ║
║   ██║  ██║╚██████╔╝   ██║   ╚██████╔╝██║ ╚═╝ ██║╚██████╔╝██║ ╚████║ ║
║   ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝ ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ ║
║                                                                  ║
║         AUTONOMOUS INSTITUTIONAL TRADING AI SYSTEM               ║
║                       v3.0 - Scanning Mode                       ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """
        self.console.print(banner, style="bold cyan")
        self.console.print(Rule(style="blue"))
