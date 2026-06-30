"""
Master Coordinator / Orchestrator
Manages agent registration, query routing, and cross-agent coordination.
"""
import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from core.memory import SharedMemory, MemoryEntry
import logging

logger = logging.getLogger(__name__)

class EmergencyMonitor:
    """
    Independent daemon that monitors account equity and triggers SYSTEM_HALT
    if a 5% drawdown occurs within a rolling 24-hour window.
    """
    def __init__(self, coordinator: 'MasterCoordinator'):
        self.coordinator = coordinator
        self.memory = coordinator.memory
        self.equity_history = []  # list of (timestamp, equity_value)
        self._is_running = False

    async def start(self):
        self._is_running = True
        logger.info("🛡️ Starting Emergency Circuit Breaker Daemon...")
        
        while self._is_running:
            try:
                # Fetch current equity
                equity = self.memory.get("account_equity")
                if equity is not None:
                    now = datetime.now().timestamp()
                    self.equity_history.append((now, float(equity)))
                    
                    # Remove entries older than 24 hours (86400 seconds)
                    self.equity_history = [e for e in self.equity_history if now - e[0] <= 86400]
                    
                    if self.equity_history:
                        max_equity = max([e[1] for e in self.equity_history])
                        drawdown = (max_equity - float(equity)) / max_equity
                        
                        if drawdown > 0.05:
                            logger.critical(f"🚨 BLACK SWAN DETECTED! Drawdown: {drawdown*100:.2f}% (Limit: 5%)")
                            await self.trigger_system_halt()
                            
                # SRE Heartbeat: Update the proof-of-life timestamp
                self.memory.store("last_active_timestamp", datetime.now().timestamp(), agent="orchestrator")
                
                await asyncio.sleep(5)  # Check every 5 seconds for rapid response
            except Exception as e:
                logger.error(f"Error in EmergencyMonitor: {e}")
                await asyncio.sleep(5)

    async def trigger_system_halt(self):
        logger.critical("🚨 INITIATING SYSTEM HALT AND EMERGENCY LIQUIDATION!")
        self.coordinator.is_halted = True
        self._is_running = False
        
        # Dispatch emergency payload to execution stream
        try:
            from tools.execution_tools import execution_stream
            # Assuming live mode for emergency, though in practice it could be configurable
            mode = self.memory.get("trading_mode", "paper")
            await execution_stream.submit_order({
                "action": "LIQUIDATE_ALL",
                "mode": mode
            })
            logger.critical("🚨 LIQUIDATION PAYLOAD DISPATCHED.")
        except Exception as e:
            logger.error(f"Could not dispatch liquidation payload: {e}")


class AgentStatus(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class AgentCapability:
    """Describes what an agent can do."""
    name: str
    description: str
    supported_operations: List[str]
    dependencies: List[str] = field(default_factory=list)
    time_estimate: float = 1.0  # seconds


@dataclass
class QueryIntent:
    """Parsed user query intent."""
    action: str
    target_agents: List[str]
    parameters: Dict[str, Any]
    priority: int = 1
    context: Optional[str] = None


class MasterCoordinator:
    """
    Master coordinator that routes queries to appropriate agents,
    manages shared memory state, and enforces data consistency.
    """

    def __init__(self):
        self.memory = SharedMemory()
        self._agents: Dict[str, Any] = {}
        self._capabilities: Dict[str, AgentCapability] = {}
        self._query_history: List[Dict] = []
        self._lock = asyncio.Lock()
        self._dependency_graph: Dict[str, List[str]] = {}
        self.is_halted = False
        self.emergency_monitor = EmergencyMonitor(self)

    def start_daemons(self):
        """Starts independent orchestrator daemons like the Emergency Circuit Breaker."""
        asyncio.create_task(self.emergency_monitor.start())

    def register_agent(self, name: str, agent: Any, capability: AgentCapability):
        """Register an agent with the coordinator."""
        self._agents[name] = agent
        self._capabilities[name] = capability
        # Build dependency graph
        for dep in capability.dependencies:
            if dep not in self._dependency_graph:
                self._dependency_graph[dep] = []
            self._dependency_graph[dep].append(name)
        self.memory.store(f"agent:{name}:status", "idle", agent="coordinator")

    def unregister_agent(self, name: str):
        """Unregister an agent."""
        self._agents.pop(name, None)
        self._capabilities.pop(name, None)

    def _detect_intent(self, query: str, context: Optional[Dict] = None) -> QueryIntent:
        """
        Simple intent detection based on keyword matching.
        In production, this would use an LLM classifier.
        """
        query_lower = query.lower()
        target_agents = []
        parameters = {"query": query, "timestamp": datetime.now().isoformat()}

        # Map keywords to agent types
        if any(word in query_lower for word in ["price", "market", "data", "fetch", "ohlcv", "ticker"]):
            target_agents.append("data")
        if any(word in query_lower for word in ["technical", "indicator", "rsi", "macd", "signal", "analysis"]):
            target_agents.append("quant")
        if any(word in query_lower for word in ["regime", "trend", "volatility", "state"]):
            target_agents.append("regime")
        if any(word in query_lower for word in ["fundamental", "earnings", "sec", "filing", "news", "sentiment"]):
            target_agents.append("research")
        if any(word in query_lower for word in ["risk", "var", "exposure", "stress", "portfolio"]):
            target_agents.append("risk")
        if any(word in query_lower for word in ["execute", "trade", "buy", "sell", "order"]):
            target_agents.append("execution")
            if "rl_agent" not in target_agents: # RL agent might inform trade decisions
                target_agents.append("rl_agent")
            if "portfolio" not in target_agents:
                target_agents.append("portfolio")
            if "compliance" not in target_agents:
                target_agents.append("compliance")
        if any(word in query_lower for word in ["review", "performance"]):
            target_agents.append("review")
        if "analyze" in query_lower or "should i" in query_lower:
            if "supervisor" not in target_agents:
                target_agents.append("supervisor")

        # Check for external agent context
        if context and "external_agent_id" in context:
            action = "external_agent_query"
        # Default to core analytical agents if no specific intent
        if not target_agents:
            target_agents = [k for k in self._agents.keys() if k not in ['execution', 'algo', 'tca', 'review', 'portfolio', 'compliance', 'cio', 'governance']]

        action = "analyze"
        if "buy" in query_lower or "sell" in query_lower:
            action = "trade"
        elif "risk" in query_lower:
            action = "assess_risk"

        return QueryIntent(
            action=action,
            target_agents=target_agents,
            parameters=parameters,
            context=query
        )

    def _resolve_dependencies(self, target_agents: List[str]) -> List[str]:
        """Resolve dependencies to determine execution order."""
        execution_order = []
        visited = set()

        def visit(agent: str):
            if agent in visited:
                return
            visited.add(agent)
            # Add dependencies first
            if agent in self._capabilities:
                for dep in self._capabilities[agent].dependencies:
                    if dep in self._agents and dep not in visited:
                        visit(dep)
            execution_order.append(agent)

        for agent in target_agents:
            visit(agent)

        return execution_order

    async def route_query(self, query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Route a natural language query to the appropriate agents.
        Returns consolidated results.
        """
        if self.is_halted:
            logger.warning("🚨 SYSTEM HALTED. Query rejected.")
            return {"error": "SYSTEM_HALTED", "message": "Circuit breaker triggered. Manual restart required."}

        async with self._lock:
            intent = self._detect_intent(query, context)
            execution_order = self._resolve_dependencies(intent.target_agents)

            # Ensure supervisor is always last among the analytical agents
            if 'supervisor' in execution_order:
                execution_order.remove('supervisor')
                execution_order.append('supervisor')
            
            # Ensure RL agent runs after analytical agents but before portfolio/execution
            if 'rl_agent' in execution_order:
                execution_order.remove('rl_agent')
                execution_order.insert(execution_order.index('supervisor') + 1, 'rl_agent')
                
            # Ensure Governance agent runs after RL agent
            if 'governance' in execution_order:
                execution_order.remove('governance')
                if 'rl_agent' in execution_order:
                    execution_order.insert(execution_order.index('rl_agent') + 1, 'governance')
                else:
                    execution_order.insert(execution_order.index('supervisor') + 1, 'governance')

            # Ensure CIO runs after supervisor
            if 'cio' in execution_order:
                execution_order.remove('cio')
                execution_order.insert(execution_order.index('supervisor') + 1, 'cio')

            # Ensure portfolio manager runs after CIO
            if 'portfolio' in execution_order:
                execution_order.remove('portfolio')
                if 'cio' in execution_order:
                    execution_order.insert(execution_order.index('cio') + 1, 'portfolio')
                else:
                    execution_order.insert(execution_order.index('supervisor') + 1, 'portfolio')
                
            # Ensure compliance runs after portfolio
            if 'compliance' in execution_order:
                execution_order.remove('compliance')
                if 'portfolio' in execution_order:
                    execution_order.insert(execution_order.index('portfolio') + 1, 'compliance')
                else:
                    execution_order.insert(execution_order.index('supervisor') + 1, 'compliance')

            # Ensure execution routing is in place
            if 'execution' in execution_order:
                execution_order.remove('execution')
                execution_order.append('execution')
                
            # Ensure algo runs after execution
            if 'algo' in execution_order:
                execution_order.remove('algo')
                execution_order.append('algo')
                
            # Ensure TCA runs after algo
            if 'tca' in execution_order:
                execution_order.remove('tca')
                execution_order.append('tca')

            # Store query metadata
            query_timestamp = datetime.now().timestamp()
            query_id = f"query:{query_timestamp}"
            
            self.memory.publish("processing_status", {"is_processing": True}, sender="coordinator")
            self.memory.store(query_id, {
                "intent": intent.action,
                "agents": execution_order,
                "context": context or {}
            }, agent="coordinator")

            results = {}
            errors = []

            async def execute_agent(agent_name: str, current_results: Dict) -> None:
                if agent_name not in self._agents:
                    return

                # Update agent status
                current_tasks = self._capabilities[agent_name].time_estimate # Placeholder for actual task count
                self.memory.store(f"agent:{agent_name}:status", "active", agent="coordinator") # Update internal memory
                self.memory.publish("agent_status_update", {
                    "agent_name": agent_name, "status": "active", "tasks": current_tasks
                }, sender="coordinator")
                self.memory.publish("activity_log_entry", {"agent": agent_name, "task": f"Starting {intent.action}", "status": "active"}, sender="coordinator")

                try:
                    agent = self._agents[agent_name]
                    # Prepare context from shared memory
                    agent_context = self._gather_context(agent_name, execution_order, current_results)

                    # Execute agent
                    if asyncio.iscoroutinefunction(agent.execute):
                        result = await agent.execute(intent.parameters, agent_context)
                    else:
                        result = agent.execute(intent.parameters, agent_context)

                    current_results[agent_name] = result

                    # Publish specific results to shared memory for TUI updates
                    if agent_name == "data" and "market" in result.get("data", {}):
                        self.memory.publish("market_data_update", result["data"]["market"], sender=agent_name)
                        self.memory.publish("sentiment_update", {
                            "sentiment": result["data"].get("news", {}).get("sentiment_classification", "Neutral"),
                            "fear_greed": result["data"].get("news", {}).get("fear_greed_index", 50)
                        }, sender=agent_name)
                    elif agent_name == "quant" and "signal" in result:
                        self.memory.publish("signal_update", {
                            "signal": result["signal"],
                            "strength": result.get("confidence", 0.0),
                            "reasons": result.get("reasons", [])
                        }, sender=agent_name)
                    elif agent_name == "risk" and "risk_assessment" in result:
                        risk_data = result["risk_assessment"]
                        var_95 = risk_data.get("var", {}).get("var", 0)
                        self.memory.publish("risk_metrics_update", {
                            "var_95": var_95,
                            "max_drawdown": result.get("max_drawdown", 0.0),
                            "sl_tp": result.get("trade_limits", {"stop_loss": 0, "take_profit": 0})
                        }, sender=agent_name)
                    elif agent_name == "supervisor" and "final_signal" in result:
                        self.memory.publish("final_signal_update", {
                            "signal": result["final_signal"],
                            "confidence": result.get("final_confidence", 0.0),
                            "reason": result.get("reasoning", "")
                        }, sender=agent_name)
                    elif agent_name == "review" and "review" in result:
                        self.memory.publish("performance_review_update", result["review"], sender=agent_name)
                    elif agent_name == "rl_agent" and "action" in result:
                        self.memory.publish("rl_decision_update", result, sender=agent_name)

                    # Store result in shared memory
                    self.memory.store(f"result:{agent_name}:{query_id}", result, agent=agent_name)

                    # Update status
                    self.memory.store(f"agent:{agent_name}:status", "idle", agent="coordinator") # Update internal memory
                    self.memory.publish("agent_status_update", {
                        "agent_name": agent_name, "status": "idle", "tasks": current_tasks + 1 # Increment task count
                    }, sender="coordinator")
                    self.memory.publish("activity_log_entry", {"agent": agent_name, "task": f"Completed {intent.action}", "status": "completed"}, sender="coordinator")

                except Exception as e:
                    errors.append(f"{agent_name}: {str(e)}")
                    self.memory.store(f"agent:{agent_name}:status", "error", agent="coordinator")
                    self.memory.publish("agent_status_update", {"agent_name": agent_name, "status": "error"}, sender="coordinator")
                    self.memory.publish("activity_log_entry", {"agent": agent_name, "task": f"Failed {intent.action}", "status": "failed"}, sender="coordinator")

            async def run_fast_lane():
                fast_lane_agents = [a for a in execution_order if a in ["data", "quant", "risk"]]
                for agent_name in fast_lane_agents:
                    await execute_agent(agent_name, results)
                return results

            async def run_slow_lane():
                # Any agent not in the fast lane goes to the slow lane background task
                slow_lane_agents = [a for a in execution_order if a not in ["data", "quant", "risk"]]
                for agent_name in slow_lane_agents:
                    await execute_agent(agent_name, results)
                
                # Consolidate results again after slow lane finishes to store final in memory
                final_consolidated = self._consolidate_results(results, errors, intent)
                self.memory.store(f"final:{query_id}", final_consolidated, agent="coordinator")
                self.memory.publish("processing_status", {"is_processing": False}, sender="coordinator")

            # Execute fast lane in the foreground
            await run_fast_lane()
            
            # Execute slow lane in the background without blocking
            asyncio.create_task(run_slow_lane())

            # Consolidate and return fast lane results immediately
            consolidated = self._consolidate_results(results, errors, intent)
            self.memory.store(f"final:{query_id}_fast", consolidated, agent="coordinator")

            return consolidated

    def _gather_context(self, current_agent: str, all_agents: List[str], results: Dict) -> Dict:
        """Gather relevant context from previous agent results."""
        context = {}
        # Find dependencies of current agent
        deps = self._capabilities.get(current_agent, AgentCapability(
            name=current_agent, description="", supported_operations=[]
        )).dependencies

        # Include results from dependencies
        for dep in deps:
            if dep in results:
                context[dep] = results[dep]

        # Include shared memory entries
        context["shared_memory"] = self.memory.get_agent_memory(current_agent)

        return context

    def _consolidate_results(self, results: Dict, errors: List, intent: QueryIntent) -> Dict:
        """Consolidate results from multiple agents into final output."""
        return {
            "intent": intent.action,
            "target_agents": intent.target_agents,
            "results": results,
            "errors": errors if errors else None,
            "timestamp": datetime.now().isoformat(),
            "success": len(errors) == 0
        }

    def get_agent_status(self) -> Dict[str, str]:
        """Get status of all registered agents."""
        status = {}
        for name in self._agents:
            status[name] = self.memory.get(f"agent:{name}:status", "idle")
        return status

    def get_query_history(self, limit: int = 10) -> List[Dict]:
        """Get recent query history."""
        return self._query_history[-limit:]


# Global coordinator instance
coordinator = MasterCoordinator()
