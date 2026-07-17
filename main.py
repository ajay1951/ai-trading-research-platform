"""
Main entry point for Multi-Agent Financial Intelligence System.
Integrates orchestrator, agents, dashboard, NL interface, and terminal UI.
"""
import asyncio
import json
import os
import time
from dotenv import load_dotenv
from typing import Optional, Dict, Any

from core.orchestrator import coordinator
from core.nl_interface import nl_interface, ParsedQuery
from core.memory import get_memory
from core.storage import data_manager

# Agent imports
from agents.data_agent import RealTimeDataAgent
from agents.quant_agent import QuantitativeAnalysisAgent
from agents.research_agent import FundamentalResearchAgent
from agents.risk_agent import RiskAgent
from agents.multistyle_trading_agent import MultiStyleTradingAgent
from agents.supervisor_agent import SupervisorAgent
from agents.cio_agent import CIOAgent
from agents.execution_agent import ExecutionAgent
from agents.execution_algo_agent import ExecutionAlgoAgent
from agents.tca_agent import TCAAgent
from agents.regime_agent import RegimeAgent
from agents.rl_agent import RLAgent
from agents.model_governance_agent import ModelGovernanceAgent
from agents.portfolio_management_agent import PortfolioManagementAgent
from agents.performance_review_agent import PerformanceReviewAgent
from agents.compliance_agent import ComplianceAgent

# Dashboard imports
from dashboard.dashboard_server import run_dashboard, dashboard_state

# Terminal UI imports
from terminal_ui import TerminalDashboard
terminal_dashboard = TerminalDashboard()

# Load environment
load_dotenv()
if not os.getenv("OPENROUTER_API_KEY"):
    raise ValueError("Missing OPENROUTER_API_KEY in .env file!")


class FinancialIntelligenceSystem:
    """
    Main system coordinator that initializes all agents,
    connects data storage, and provides CLI/API/TUI interfaces.
    """
    
    def __init__(self, enable_dashboard: bool = True, enable_tui: bool = False,
                 use_redis: bool = False, use_chromadb: bool = False,
                 use_influxdb: bool = False, live_trading: bool = False, enable_rl: bool = False):
        self.coordinator = coordinator
        self.nl_interface = nl_interface
        self.memory = get_memory()
        self.data_manager = data_manager
        self.enable_dashboard = enable_dashboard
        self.enable_tui = enable_tui
        self.live_trading = live_trading
        self.last_analysis_result: Optional[Dict[str, Any]] = None
        if self.live_trading:
            print("\n" + "="*60)
            print("  [WARNING] LIVE TRADING IS ENABLED. REAL ORDERS WILL BE PLACED.")
            print("="*60 + "\n")
        self.enable_rl = enable_rl
        self.dashboard_thread = None
        self.tui_thread = None
        self.tui_agent_map = {
            "data": "Data Engineer",
            "regime": "Market Regime",
            "research": "Researcher",
            "quant": "Quant",
            "portfolio": "Portfolio Manager",
            "cio": "CIO",
            "compliance": "Compliance",
            "risk": "Risk CRO",
            "execution": "Execution Router",
            "algo": "Algo Execution",
            "tca": "TCA Analyst",
            "rl_agent": "RL Agent",
            "governance": "Governance",
            "supervisor": "Supervisor",
            "review": "Reviewer"
        }
        
        # Initialize data storage
        self._init_storage(use_redis, use_chromadb, use_influxdb)
        
        # Register agents with coordinator
        self._register_agents()
        
        print("[INIT] Financial Intelligence System initialized")
    
    def _init_storage(self, use_redis: bool, use_chromadb: bool, use_influxdb: bool):
        """Initialize data storage backends."""
        print("[INIT] Connecting to data storage...")
        results = self.data_manager.connect_all()
        
        for backend, success in results.items():
            status = "connected" if success else "unavailable"
            print(f"  {backend}: {status}")
        
        if not any(results.values()):
            print("  Storage: using in-memory fallback")
    
    def _register_agents(self):
        """Register all specialized agents with coordinator."""
        agents = {
            "data": RealTimeDataAgent(get_memory()),
            "regime": RegimeAgent(get_memory()),
            "quant": QuantitativeAnalysisAgent(get_memory()),
            "research": FundamentalResearchAgent(get_memory()),
            "risk": RiskAgent(get_memory()),
            "multistyle": MultiStyleTradingAgent(get_memory()),
            "supervisor": SupervisorAgent(get_memory()),
            "cio": CIOAgent(get_memory()),
            "portfolio": PortfolioManagementAgent(get_memory()),
            "review": PerformanceReviewAgent(get_memory()),
            "rl_agent": RLAgent(get_memory()),
            "governance": ModelGovernanceAgent(get_memory()),
            "compliance": ComplianceAgent(get_memory()),
            "execution": ExecutionAgent(get_memory(), live_trading=self.live_trading),
            "algo": ExecutionAlgoAgent(get_memory()),
            "tca": TCAAgent(get_memory())
        }
        
        # If RL is enabled, tell the portfolio agent to use it
        if self.enable_rl and "portfolio" in agents:
            agents["portfolio"].rl_enabled = True
            print("[INIT] RLAgent integration enabled for PortfolioManagementAgent.")

        capabilities = {
            "data": {
                "name": "data_retrieval",
                "description": "Fetches real-time market data, news, SEC filings",
                "supported_operations": ["fetch_market_data", "fetch_news", "fetch_filings"],
                "dependencies": []
            },
            "regime": {
                "name": "market_regime_detection",
                "description": "Detects current market regime to provide context for other agents",
                "supported_operations": ["detect_regime"],
                "dependencies": ["data"]
            },
            "quant": {
                "name": "quantitative_analysis",
                "description": "Calculates technical indicators and trading signals",
                "supported_operations": ["calculate_indicators", "generate_signal", "backtest"],
                "dependencies": ["data", "regime"]
            },
            "research": {
                "name": "fundamental_research",
                "description": "Analyzes earnings, sentiment, and macro trends",
                "supported_operations": ["analyze_earnings", "macro_sentiment", "sec_analysis"],
                "dependencies": ["data", "regime"]
            },
            "risk": {
                "name": "risk_management",
                "description": "Calculates VaR, stress tests, and risk limits",
                "supported_operations": ["calculate_var", "stress_test", "exposure_analysis"],
                "dependencies": ["data", "quant", "regime"]
            },
            "multistyle": {
                "name": "multistyle_trade_planning",
                "description": "Generates comprehensive trading roadmaps for scalping, intraday, swing, and position styles.",
                "supported_operations": ["generate_roadmap"],
                "dependencies": ["data"]
            },
            "supervisor": {
                "name": "supervisor",
                "description": "Reviews all agent outputs, detects conflicts, and forms a final consolidated opinion.",
                "supported_operations": ["consolidate", "review"],
                "dependencies": ["multistyle", "data", "quant", "research", "risk"], # Supervisor now also depends on the new multistyle agent
            },
            "cio": {
                "name": "chief_investment_officer",
                "description": "Calculates optimal fund-level allocations and target weights.",
                "supported_operations": ["calculate_targets"],
                "dependencies": ["supervisor"]
            },
            "portfolio": {
                "name": "portfolio_management",
                "description": "Determines trade size and manages portfolio risk based on CIO's target weights.",
                "supported_operations": ["determine_trade_size"],
                "dependencies": ["cio"]
            },
            "review": {
                "name": "performance_review",
                "description": "Periodically reviews trading performance and provides feedback.",
                "supported_operations": ["review_performance"],
                "dependencies": []
            },
            "rl_agent": {
                "name": "reinforcement_learning_agent",
                "description": "Deep Q-Network learning optimal trading actions.",
                "supported_operations": ["train", "predict_action"],
                "dependencies": ["data", "quant", "research", "risk", "regime"] 
            },
            "governance": {
                "name": "model_governance",
                "description": "Monitors RL model drift and ensures safety.",
                "supported_operations": ["validate_model"],
                "dependencies": ["rl_agent"]
            },
            "compliance": {
                "name": "compliance_management",
                "description": "Checks pre-trade risk and enforces institutional mandates.",
                "supported_operations": ["validate_trade"],
                "dependencies": ["portfolio"]
            },
            "execution": {
                "name": "trade_execution",
                "description": "Routes approved trades to the algorithmic execution layer.",
                "supported_operations": ["execute_trade"],
                "dependencies": ["compliance"]
            },
            "algo": {
                "name": "algo_execution",
                "description": "Slices large parent orders into TWAP/VWAP child orders.",
                "supported_operations": ["slice_order"],
                "dependencies": ["execution"]
            },
            "tca": {
                "name": "trade_cost_analysis",
                "description": "Calculates slippage and market impact post-execution.",
                "supported_operations": ["analyze_cost"],
                "dependencies": ["algo"]
            }
        }
        
        # # Store agent instances in memory for cross-agent access (e.g., Portfolio accessing RLAgent)
        # for agent_name, agent_instance in agents.items():
        #     self.memory.store(f"agent_instance:{agent_name}", agent_instance)

        for agent_name, agent in agents.items():
            cap = capabilities[agent_name]
            from core.orchestrator import AgentCapability
            self.coordinator.register_agent(
                agent_name,
                agent,
                AgentCapability(**cap)
            )
        
        print(f"[INIT] Registered {len(agents)} agents")
    
    def start_dashboard(self):
        """Start web dashboard in background thread."""
        if self.enable_dashboard:
            import threading
            # When running in Docker, the server must bind to 0.0.0.0 to be
            # accessible from the host machine. Otherwise, default to localhost.
            host = "0.0.0.0" if os.getenv("DOCKER_ENV") == "true" else "127.0.0.1"
            self.dashboard_thread = threading.Thread(
                target=run_dashboard,
                kwargs={"host": host, "port": 8000},
                daemon=True
            )
            self.dashboard_thread.start()
            # The user always accesses the dashboard via localhost from their browser.
            print("[DASHBOARD] Running on http://localhost:8000")
    
    def start_tui(self):
        """Start terminal UI in background thread."""
        if self.enable_tui:
            import threading
            self.tui_thread = threading.Thread(
                target=self._run_tui_loop,
                daemon=True
            )
            self.tui_thread.start()
            print("[TUI] Terminal Dashboard starting...")
    
    def _run_tui_loop(self):
        """Run the TUI event loop."""
        try:
            terminal_dashboard.start()
            while self.enable_tui and terminal_dashboard.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"TUI error: {e}")
    
    async def analyze(self, query: str, symbol: Optional[str] = None) -> Dict:
        """
        Run full analysis for a symbol or query.
        """
        print(f"\n{'='*60}")
        print(f"[ANALYSIS] Processing: {query}")
        print(f"{'='*60}")
        
        # Update TUI if running
        if self.enable_tui:
            terminal_dashboard.set_processing(True)
            terminal_dashboard.log_task("System", f"Query: {query[:30]}...", "started")
        
        # Parse query
        parsed = self.nl_interface.parse_query(query)
        if symbol:
            parsed.entities['symbol'] = symbol
        
        # Execute through orchestrator
        result = await self.coordinator.route_query(query)
        self.last_analysis_result = result
        
        # Update TUI with results
        if self.enable_tui:
            self._update_tui_with_results(result)
        
        # Generate formatted output
        formatted = self.nl_interface.generate_response(result, parsed)
        
        # Print to console
        print("\n" + formatted)
        print("\n")
        
        return result
    
    def _update_tui_with_results(self, result: Dict):
        """Update TUI display with analysis results."""
        try:
            agent_results = result.get("results", {})
            
            # Update agent statuses
            for agent_name in agent_results:
                tui_agent_name = self.tui_agent_map.get(agent_name)
                if tui_agent_name and tui_agent_name in terminal_dashboard.agent_status:
                    terminal_dashboard.update_agent(
                        tui_agent_name,
                        "active", 
                        task="completed"
                    )
            
            # Extract signal from quant agent
            quant_result = agent_results.get("quant", {})
            if quant_result:
                analysis = quant_result.get("analysis", {})
                signal_data = analysis.get("signal", {})
                terminal_dashboard.set_signal(
                    signal_data.get("signal", "HOLD"),
                    signal_data.get("strength", 0.5),
                    signal_data.get("reasons", [])
                )
            
            # Extract sentiment from research agent
            research_result = agent_results.get("research", {})
            if research_result:
                research_data = research_result.get("research", {})
                macro = research_data.get("macro_sentiment", {})
                terminal_dashboard.set_sentiment(
                    macro.get("overall_sentiment", "Neutral"),
                    macro.get("fear_greed_index", 50)
                )
            
            # Extract risk from risk agent
            risk_result = agent_results.get("risk", {})
            if risk_result:
                risk_data = risk_result.get("risk_assessment", {})
                var = risk_data.get("var", {}).get("var", 0)
                stress = risk_data.get("stress_tests", {})
                worst = stress.get("worst_case", {})
                sl_tp = risk_data.get("trade_limits", {})
                terminal_dashboard.set_risk_metrics(
                    var,
                    abs(worst.get("impact_pct", 0)),
                    sl_tp
                )
            
            terminal_dashboard.log_task("System", "Analysis complete", "completed")
            terminal_dashboard.set_processing(False)
            
        except Exception as e:
            print(f"TUI update error: {e}")
    
    def analyze_sync(self, query: str, symbol: Optional[str] = None) -> Dict:
        """Synchronous wrapper for analyze."""
        return asyncio.run(self.analyze(query, symbol))
    
    def run_interactive_cli(self):
        """Run interactive CLI session (text-only, no TUI)."""
        print("\n" + "="*60)
        print("Financial Intelligence System - Interactive Mode")
        print("="*60)
        print("Enter queries or commands. Type 'exit' to quit.")
        print("Example: 'Analyze BTC/USDT for risk and generate signal'")
        print()
        
        while True:
            try:
                user_input = input("\nQuery> ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ('exit', 'quit', 'q'):
                    break
                
                if user_input.startswith('/'):
                    self._handle_command(user_input)
                    continue
                
                result = self.analyze_sync(user_input)
                
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")
    
    def run_tui_interactive(self):
        """Run interactive mode with TUI updates."""
        print("\n" + "="*60)
        print("Financial Intelligence System - TUI Mode")
        print("="*60)
        print("Press [Ctrl+C] to exit")
        print()
        
        self.start_tui()
        
        try:
            while True:
                user_input = input("\nQuery> ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ('exit', 'quit', 'q'):
                    break
                
                if user_input.startswith('/'):
                    self._handle_command(user_input)
                    continue
                
                result = self.analyze_sync(user_input)
                
        except KeyboardInterrupt:
            print("\nShutting down TUI...")
        finally:
            terminal_dashboard.running = False
            if self.tui_thread:
                self.tui_thread.join(timeout=2)
    
    def _handle_command(self, command: str):
        """Handle CLI commands."""
        parts = command.split()
        cmd = parts[0].lower()
        
        if cmd == '/symbol':
            if len(parts) > 1:
                symbol = parts[1].upper()
                dashboard_state.current_symbol = symbol
                terminal_dashboard.current_symbol = symbol
                print(f"Symbol set to: {symbol}")
            else:
                print(f"Current symbol: {terminal_dashboard.current_symbol}")
        
        elif cmd == '/tui':
            if terminal_dashboard.running:
                terminal_dashboard.running = False
                print("TUI stopped")
            else:
                self.start_tui()
                print("TUI started")
        
        elif cmd == '/agents':
            print("\nRegistered Agents:")
            for name, agent in self.coordinator._agents.items():
                cap = self.coordinator._capabilities.get(name)
                if cap:
                    print(f"  - {name}: {cap.description}")
                    print(f"    Operations: {', '.join(cap.supported_operations)}")
        
        elif cmd == '/memory':
            keys = get_memory().get_all_keys()
            print(f"\nMemory contains {len(keys)} keys")
            if keys:
                print("Recent keys:")
                for k in keys[-10:]:
                    print(f"  - {k}")
        
        elif cmd == '/clear':
            get_memory().clear()
            print("Memory cleared")
        
        elif cmd == '/report':
            if self.last_analysis_result:
                try:
                    from core.reporting import generate_pdf_report
                    filepath = generate_pdf_report(self.last_analysis_result)
                    print(f"\n[SUCCESS] PDF report generated: {filepath}")
                except Exception as e:
                    print(f"\n[ERROR] Failed to generate PDF report: {e}")
            else:
                print("\n[INFO] No analysis has been run yet. Please run a query first.")

        elif cmd == '/help':
            print("\nCommands:")
            print("  /symbol [SYMBOL]  - Set trading symbol (e.g., BTC/USDT)")
            print("  /tui              - Start/stop terminal dashboard")
            print("  /agents           - List all agents and capabilities")
            print("  /memory           - Show memory keys")
            print("  /clear            - Clear shared memory")
            print("  /report           - Generate a PDF report of the last analysis")
            print("  /help             - Show this help")
            print("\nNatural Language Queries:")
            print("  'Analyze BTC/USDT and tell me if I should buy'")
            print("  'What's the risk exposure for ETH?'")
            print("  'Fetch latest news for BTC and determine sentiment'")
        
        else:
            print(f"Unknown command: {cmd}. Type /help for available commands.")


# Module-level singleton for imports
_system_instance = None

def get_system(**kwargs) -> FinancialIntelligenceSystem:
    """Get or create the global system instance."""
    global _system_instance
    if _system_instance is None:
        _system_instance = FinancialIntelligenceSystem(**kwargs)
    return _system_instance

# Convenience instance for simple imports (created lazily on first access)
class _LazySystem:
    def __getattr__(self, name):
        # Create default system on first attribute access
        system = get_system()
        return getattr(system, name)

# Export lazy singleton for backward compatibility
system = _LazySystem()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Multi-Agent Financial Intelligence System")
    parser.add_argument('--query', '-q', type=str, help='Natural language query to process')
    parser.add_argument('--symbol', '-s', type=str, default="BTC/USDT", help='Trading symbol (default: BTC/USDT)')
    parser.add_argument('--interactive', '-i', action='store_true', help='Run in interactive CLI mode')
    parser.add_argument('--tui', '-t', action='store_true', help='Run with Terminal UI (Bloomberg-style)')
    parser.add_argument('--no-dashboard', action='store_true', help='Disable web dashboard')
    parser.add_argument('--no-tui', action='store_true', help='Disable terminal UI')
    parser.add_argument('--enable-rl', action='store_true', help='Enable Reinforcement Learning agent integration.')
    parser.add_argument('--live', action='store_true', help='Enable live trading mode. USE WITH CAUTION.')
    parser.add_argument('--daemon', action='store_true', help='Run in a non-interactive daemon mode (for Docker).')
    
    args = parser.parse_args()
    
    # Create system instance
    global system
    system = FinancialIntelligenceSystem(
        enable_dashboard=not args.no_dashboard,
        enable_tui=args.tui,
        use_redis=os.getenv("USE_REDIS", "false").lower() == "true",
        use_chromadb=os.getenv("USE_CHROMADB", "false").lower() == "true",
        use_influxdb=os.getenv("USE_INFLUXDB", "false").lower() == "true", 
        enable_rl=args.enable_rl,
        live_trading=args.live
    )
    
    # Start services
    if not args.no_dashboard:
        system.start_dashboard()
    
    if args.query:
        system.analyze_sync(args.query, args.symbol)
    elif args.interactive:
        system.run_interactive_cli()
    elif args.tui:
        system.run_tui_interactive()
    elif args.daemon:
        print("[DAEMON] System running in daemon mode. Press Ctrl+C to exit from logs.")
        try:
            # Keep the main thread alive for daemon threads like the dashboard
            while True:
                time.sleep(3600)  # Sleep for an hour and loop
        except KeyboardInterrupt:
            print("\n[DAEMON] Shutting down.")
    else:
        # Default: run interactive CLI
        system.run_interactive_cli()


if __name__ == "__main__":
    main()
