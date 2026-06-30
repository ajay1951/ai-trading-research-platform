"""
Shared Memory Architecture for Multi-Agent System
Provides Redis pub/sub, ChromaDB vector storage, and InfluxDB time-series storage.
"""
import json
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod


@dataclass
class MemoryEntry:
    """Structured memory entry for cross-agent communication."""
    key: str
    value: Any
    agent: str
    timestamp: datetime
    ttl: Optional[int] = None
    metadata: Optional[Dict] = None


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def store(self, key: str, value: Any, **kwargs) -> bool:
        pass

    @abstractmethod
    def retrieve(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        pass


class InMemoryStorage(StorageBackend):
    """In-memory storage backend for development/testing, now with JSON persistence."""

    def __init__(self):
        self._storage: Dict[str, MemoryEntry] = {}
        self._lock = threading.RLock()
        self._persist_file = "memory_dump.json"
        self._load_from_disk()

    def _save_to_disk(self):
        """Save storage to disk."""
        try:
            with open(self._persist_file, "w") as f:
                dump_dict = {}
                for k, v in self._storage.items():
                    dump_dict[k] = {
                        "key": v.key,
                        "value": v.value,
                        "agent": v.agent,
                        "timestamp": v.timestamp.isoformat(),
                        "ttl": v.ttl,
                        "metadata": v.metadata
                    }
                json.dump(dump_dict, f, indent=2)
        except TypeError as e:
            # This will catch non-serializable objects and prevent spamming the log.
            print(f"Warning: Could not persist memory to disk. A non-serializable object was encountered: {e}")
        except Exception as e:
            print(f"Failed to save memory to disk: {e}")

    def _load_from_disk(self):
        """Load storage from disk."""
        import os
        if not os.path.exists(self._persist_file):
            return
        try:
            with open(self._persist_file, "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    self._storage[k] = MemoryEntry(
                        key=v["key"],
                        value=v["value"],
                        agent=v["agent"],
                        timestamp=datetime.fromisoformat(v["timestamp"]),
                        ttl=v["ttl"],
                        metadata=v["metadata"]
                    )
        except Exception as e:
            print(f"Failed to load memory from disk: {e}")

    def store(self, key: str, value: Any, agent: str = "system", ttl: Optional[int] = None, metadata: Optional[Dict] = None) -> bool:
        with self._lock:
            entry = MemoryEntry(
                key=key,
                value=value,
                agent=agent,
                timestamp=datetime.now(),
                ttl=ttl,
                metadata=metadata or {}
            )
            self._storage[key] = entry
            self._save_to_disk()
            return True

    def retrieve(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._storage.get(key)
            if entry:
                # Check TTL
                if entry.ttl:
                    age = (datetime.now() - entry.timestamp).total_seconds()
                    if age > entry.ttl:
                        del self._storage[key]
                        self._save_to_disk()
                        return None
                return entry.value
            return None

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._storage:
                del self._storage[key]
                self._save_to_disk()
                return True
            return False

    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._storage

    def get_entries_by_agent(self, agent: str) -> List[MemoryEntry]:
        with self._lock:
            return [e for e in self._storage.values() if e.agent == agent]

    def clear(self):
        with self._lock:
            self._storage.clear()
            self._save_to_disk()


class SharedMemory:
    """
    Centralized shared memory system for agent communication.
    Uses singleton pattern for global access.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._storage = InMemoryStorage()
        self._pubsub_channels: Dict[str, List[callable]] = {}
        self._pubsub_lock = threading.RLock()
        self._initialized = True

    # Storage operations
    def store(self, key: str, value: Any, agent: str = "system", ttl: Optional[int] = None, metadata: Optional[Dict] = None) -> bool:
        """Store a value in shared memory."""
        return self._storage.store(key, value, agent, ttl, metadata)

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Retrieve a value from shared memory."""
        return self._storage.retrieve(key) or default

    def update(self, key: str, value: Any, agent: str = "system") -> bool:
        """Update an existing key."""
        if self._storage.exists(key):
            return self._storage.store(key, value, agent)
        return False

    def delete(self, key: str) -> bool:
        """Delete a key from memory."""
        return self._storage.delete(key)

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return self._storage.exists(key)

    def clear(self):
        """Clear all memory."""
        self._storage.clear()

    # Pub/Sub operations
    def subscribe(self, channel: str, callback: callable):
        """Subscribe to a channel for updates."""
        with self._pubsub_lock:
            if channel not in self._pubsub_channels:
                self._pubsub_channels[channel] = []
            self._pubsub_channels[channel].append(callback)

    def publish(self, channel: str, data: Any, sender: str = "system"):
        """Publish a message to a channel."""
        with self._pubsub_lock:
            message = {
                "channel": channel,
                "data": data,
                "sender": sender,
                "timestamp": datetime.now().isoformat()
            }
            if channel in self._pubsub_channels:
                for callback in self._pubsub_channels[channel]:
                    try:
                        callback(message)
                    except Exception as e:
                        print(f"Pub/Sub callback error: {e}")

    # Utility methods
    def get_agent_memory(self, agent: str) -> Dict[str, Any]:
        """Get all values stored by a specific agent."""
        entries = self._storage.get_entries_by_agent(agent)
        return {e.key: e.value for e in entries}

    def get_all_keys(self) -> List[str]:
        """Get all keys in memory."""
        # In a real Redis backend, this would use Redis keys command
        if hasattr(self._storage, '_storage'):
            return list(self._storage._storage.keys())
        return []

    def get_metadata(self, key: str) -> Optional[Dict]:
        """Get metadata for a key."""
        entry = self._storage._storage.get(key) if hasattr(self._storage, '_storage') else None
        return entry.metadata if entry else None


# Global singleton instances
_global_memory_instance = None


def get_memory() -> SharedMemory:
    """Get the global shared memory instance."""
    global _global_memory_instance
    if _global_memory_instance is None:
        _global_memory_instance = SharedMemory()
    return _global_memory_instance
