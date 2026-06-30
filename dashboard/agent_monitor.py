import time
import functools
from dashboard.dashboard_bridge import dashboard

def monitor_agent(name: str):
    """Decorator to monitor agent task execution"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            dashboard.update_agent(name, "active", 0, func.__name__)
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                dashboard.update_agent(name, "idle", 0)
                dashboard.log_task(name, func.__name__, "completed", duration)
                return result
            except Exception as e:
                dashboard.update_agent(name, "error", 0)
                dashboard.log_task(name, func.__name__, "failed", time.time() - start_time)
                raise
        return wrapper
    return decorator

def monitor_llm_call(agent_name: str, tokens: int = 0):
    """Monitor LLM token usage"""
    dashboard.update_agent(agent_name, "active", tokens)
    time.sleep(0.1)  # Simulate async update