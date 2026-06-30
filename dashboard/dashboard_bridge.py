import requests
import json
from datetime import datetime
from typing import Optional
import threading
import time

DASHBOARD_URL = "http://localhost:8000"

class DashboardBridge:
    def __init__(self, auto_flush=True):
        self.auto_flush = auto_flush
        self.buffer = []
        self.lock = threading.Lock()
        if self.auto_flush:
            self.thread = threading.Thread(target=self._flush_loop, daemon=True)
            self.thread.start()
        
    def _flush_loop(self):
        while True:
            time.sleep(0.5)
            with self.lock:
                if self.buffer:
                    for endpoint, data in self.buffer:
                        self._send_to_dashboard(endpoint, data, force=True)
                    self.buffer.clear()

    def update_agent(self, name: str, status: str, tokens: int, task: Optional[str] = None):
        """Send agent status update to dashboard"""
        data = {
            "name": name,
            "status": status,
            "tokens_used": tokens,
            "tasks_completed": self._increment_task(name),
            "avg_response_time": 0.0,
            "success_rate": 100.0,
            "current_task": task
        }
        self._send_to_dashboard("/agent/update", data)
    
    def log_task(self, agent: str, task: str, status: str, duration: Optional[float] = None):
        """Log task event to dashboard"""
        data = {
            "agent": agent,
            "task": task,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "duration": duration
        }
        self._send_to_dashboard("/task/event", data)
    
    def _increment_task(self, name: str) -> int:
        """Track task count per agent"""
        if not hasattr(self, '_task_counts'):
            self._task_counts = {}
        self._task_counts[name] = self._task_counts.get(name, 0) + 1
        return self._task_counts[name]
    
    def _send_to_dashboard(self, endpoint: str, data: dict, force: bool = False):
        """Send data to dashboard with buffering"""
        if self.auto_flush and not force:
            with self.lock:
                self.buffer.append((endpoint, data))
            return

        try:
            requests.post(f"{DASHBOARD_URL}{endpoint}", json=data, timeout=0.5)
        except requests.exceptions.RequestException:
            pass  # Dashboard may not be running

dashboard = DashboardBridge()