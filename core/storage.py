"""
Data Storage Layer
Integrations for Redis (pub/sub), ChromaDB (vector search), InfluxDB (time-series).
"""
import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from abc import ABC, abstractmethod

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class StorageBackend(ABC):
    """Abstract base class for storage backends."""
    
    @abstractmethod
    def connect(self) -> bool:
        pass
    
    @abstractmethod
    def disconnect(self):
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        pass


# ============ Redis Integration ============

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RedisStorage(StorageBackend):
    """Redis-backed storage for fast pub/sub and caching."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: Optional[str] = None):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.client = None
        self._connected = False
    
    def connect(self) -> bool:
        if not REDIS_AVAILABLE:
            return False
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True
            )
            self.client.ping()
            self._connected = True
            return True
        except Exception as e:
            print(f"Redis connection error: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        if self.client:
            self.client.close()
            self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected
    
    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set key-value pair with optional expiration (seconds)."""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            return bool(self.client.set(key, value, ex=ex))
        except Exception as e:
            print(f"Redis SET error: {e}")
            return False
    
    def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        try:
            return self.client.get(key)
        except Exception:
            return None
    
    def delete(self, key: str) -> bool:
        """Delete key."""
        try:
            return bool(self.client.delete(key))
        except Exception:
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            return bool(self.client.exists(key))
        except Exception:
            return False
    
    def publish(self, channel: str, message: Union[str, Dict]) -> int:
        """Publish message to channel."""
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
            return self.client.publish(channel, message)
        except Exception as e:
            print(f"Redis PUBLISH error: {e}")
            return 0
    
    def subscribe(self, channel: str, callback: callable):
        """Subscribe to channel with callback."""
        try:
            pubsub = self.client.pubsub()
            pubsub.subscribe(channel)
            for message in pubsub.listen():
                if message['type'] == 'message':
                    callback(message['data'])
        except Exception as e:
            print(f"Redis SUBSCRIBE error: {e}")
    
    def lpush(self, key: str, value: str) -> int:
        """Push to list (left)."""
        try:
            return self.client.lpush(key, value)
        except Exception:
            return 0
    
    def lrange(self, key: str, start: int = 0, end: int = -1) -> List[str]:
        """Get list range."""
        try:
            return self.client.lrange(key, start, end)
        except Exception:
            return []
    
    def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter."""
        try:
            return self.client.incr(key, amount)
        except Exception:
            return 0


# ============ ChromaDB Integration ============

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class ChromaDBStorage(StorageBackend):
    """ChromaDB vector storage for semantic search across market data."""
    
    def __init__(self, collection_name: str = "market_data", persist_dir: str = "./chroma_db"):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self.client = None
        self.collection = None
        self._connected = False
    
    def connect(self) -> bool:
        if not CHROMADB_AVAILABLE:
            return False
        try:
            self.client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.persist_dir
            ))
            self.collection = self.client.get_or_create_collection(name=self.collection_name)
            self._connected = True
            return True
        except Exception as e:
            print(f"ChromaDB connection error: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        if self.client:
            # ChromaDB persists automatically
            self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected
    
    def add_documents(self, documents: List[str], metadatas: List[Dict] = None, ids: List[str] = None):
        """Add text documents with metadata to vector store."""
        try:
            if metadatas is None:
                metadatas = [{}] * len(documents)
            if ids is None:
                ids = [f"doc_{datetime.now().timestamp()}_{i}" for i in range(len(documents))]
            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)
            return True
        except Exception as e:
            print(f"ChromaDB ADD error: {e}")
            return False
    
    def search(self, query_text: str, n_results: int = 5) -> List[Dict]:
        """Semantic search for similar documents."""
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            return self._format_search_results(results)
        except Exception as e:
            print(f"ChromaDB SEARCH error: {e}")
            return []
    
    def _format_search_results(self, results: Dict) -> List[Dict]:
        """Format ChromaDB results."""
        formatted = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                distance = results['distances'][0][i] if results['distances'] else None
                formatted.append({
                    "document": doc,
                    "metadata": metadata,
                    "distance": distance
                })
        return formatted
    
    def store_market_insight(self, symbol: str, insight: str, metadata: Dict = None):
        """Store a market insight for future retrieval."""
        doc = f"{symbol}: {insight}"
        meta = {"symbol": symbol, "timestamp": datetime.now().isoformat()}
        if metadata:
            meta.update(metadata)
        self.add_documents([doc], [meta])


# ============ InfluxDB Integration ============

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
    INFLUXDB_AVAILABLE = True
except ImportError:
    INFLUXDB_AVAILABLE = False


class InfluxDBStorage(StorageBackend):
    """InfluxDB time-series storage for historical market data."""
    
    def __init__(self, url: str = "http://localhost:8086", token: str = "", org: str = "financial_ai", bucket: str = "market_data"):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client = None
        self.write_api = None
        self.query_api = None
        self._connected = False
    
    def connect(self) -> bool:
        if not INFLUXDB_AVAILABLE:
            return False
        try:
            self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.query_api = self.client.query_api()
            # Test connection
            self.client.health()
            self._connected = True
            return True
        except Exception as e:
            print(f"InfluxDB connection error: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        if self.client:
            self.client.close()
            self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected
    
    def write_ohlcv(self, symbol: str, timeframe: str, 
                    timestamps: List[datetime], opens: List[float], highs: List[float],
                    lows: List[float], closes: List[float], volumes: List[float]):
        """Write OHLCV data to InfluxDB."""
        try:
            points = []
            for ts, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
                point = Point("market_data") \
                    .tag("symbol", symbol) \
                    .tag("timeframe", timeframe) \
                    .field("open", float(o)) \
                    .field("high", float(h)) \
                    .field("low", float(l)) \
                    .field("close", float(c)) \
                    .field("volume", float(v)) \
                    .time(ts, WritePrecision.NS)
                points.append(point)
            self.write_api.write(bucket=self.bucket, record=points)
            return True
        except Exception as e:
            print(f"InfluxDB WRITE error: {e}")
            return False
    
    def query_ohlcv(self, symbol: str, timeframe: str, start: str, stop: str = None):
        """Query OHLCV data from InfluxDB."""
        try:
            stop = stop or "now()"
            query = f'''
                from(bucket: "{self.bucket}")
                |> range(start: {start}, stop: {stop})
                |> filter(fn: (r) => r["symbol"] == "{symbol}" and r["timeframe"] == "{timeframe}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> keep(columns: ["_time", "open", "high", "low", "close", "volume"])
            '''
            result = self.query_api.query_data_frame(query=query)
            return result if result is not None else (pd.DataFrame() if PANDAS_AVAILABLE else {})
        except Exception as e:
            print(f"InfluxDB QUERY error: {e}")
            return pd.DataFrame() if PANDAS_AVAILABLE else {}
    
    def write_agent_output(self, agent: str, key: str, value: Any, tags: Dict = None):
        """Write agent output to InfluxDB for time-series tracking."""
        try:
            point = Point("agent_outputs") \
                .tag("agent", agent) \
                .tag("key", key)
            if tags:
                for k, v in tags.items():
                    point = point.tag(k, str(v))
            point = point.field("value", float(value) if isinstance(value, (int, float)) else 0)
            point = point.time(datetime.now(), WritePrecision.NS)
            self.write_api.write(bucket=self.bucket, record=point)
        except Exception as e:
            print(f"InfluxDB AGENT OUTPUT error: {e}")


# ============ Unified Data Manager ============

class DataManager:
    """
    Unified data manager that coordinates all storage backends.
    Provides fallback to in-memory if backends unavailable.
    """
    
    def __init__(self, use_redis: bool = False, use_chromadb: bool = False, use_influxdb: bool = False):
        self.redis = RedisStorage() if use_redis else None
        self.chromadb = ChromaDBStorage() if use_chromadb else None
        self.influxdb = InfluxDBStorage() if use_influxdb else None
        
        # In-memory fallback
        self._memory_cache: Dict[str, Any] = {}
        self._pubsub_listeners: Dict[str, List[callable]] = {}
    
    def connect_all(self) -> Dict[str, bool]:
        """Connect to all enabled backends."""
        results = {}
        if self.redis:
            results['redis'] = self.redis.connect()
        if self.chromadb:
            results['chromadb'] = self.chromadb.connect()
        if self.influxdb:
            results['influxdb'] = self.influxdb.connect()
        return results
    
    def store(self, key: str, value: Any, ttl: Optional[int] = None):
        """Store in all available backends."""
        # Always store in memory cache
        self._memory_cache[key] = {
            "value": value,
            "timestamp": datetime.now().isoformat()
        }
        
        if self.redis and self.redis.is_connected():
            self.redis.set(key, value, ex=ttl)
    
    def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve from cache or Redis."""
        if key in self._memory_cache:
            return self._memory_cache[key]["value"]
        if self.redis and self.redis.is_connected():
            val = self.redis.get(key)
            if val:
                try:
                    return json.loads(val)
                except:
                    return val
        return None
    
    def publish(self, channel: str, message: Any):
        """Publish to all subscribers."""
        if self.redis and self.redis.is_connected():
            self.redis.publish(channel, message)
        
        # Local callbacks
        if channel in self._pubsub_listeners:
            for callback in self._pubsub_listeners[channel]:
                try:
                    callback(message)
                except Exception as e:
                    print(f"PubSub callback error: {e}")
    
    def subscribe(self, channel: str, callback: callable):
        """Subscribe to channel."""
        if self.redis and self.redis.is_connected():
            # Would spawn thread for Redis subscription
            pass
        if channel not in self._pubsub_listeners:
            self._pubsub_listeners[channel] = []
        self._pubsub_listeners[channel].append(callback)
    
    def store_market_insight(self, symbol: str, insight: str, metadata: Dict = None):
        """Store in vector DB for semantic search."""
        if self.chromadb and self.chromadb.is_connected():
            self.chromadb.store_market_insight(symbol, insight, metadata)
    
    def search_insights(self, query: str, symbol: Optional[str] = None, n: int = 5) -> List[Dict]:
        """Search stored insights semantically."""
        if self.chromadb and self.chromadb.is_connected():
            results = self.chromadb.search(query, n_results=n)
            if symbol:
                results = [r for r in results if r["metadata"].get("symbol") == symbol]
            return results
        return []
    
    def write_market_data(self, symbol: str, timeframe: str, ohlcv_data: Dict):
        """Write OHLCV to time-series DB."""
        if self.influxdb and self.influxdb.is_connected():
            self.influxdb.write_ohlcv(
                symbol, timeframe,
                ohlcv_data['timestamps'],
                ohlcv_data['opens'],
                ohlcv_data['highs'],
                ohlcv_data['lows'],
                ohlcv_data['closes'],
                ohlcv_data['volumes']
            )
    
    def get_market_data(self, symbol: str, timeframe: str, start: str, stop: str = None):
        """Query time-series market data."""
        if self.influxdb and self.influxdb.is_connected():
            return self.influxdb.query_ohlcv(symbol, timeframe, start, stop)
        return None


# Global data manager instance (configured via env vars)
import os
USE_REDIS = os.getenv("USE_REDIS", "false").lower() == "true"
USE_CHROMADB = os.getenv("USE_CHROMADB", "false").lower() == "true"
USE_INFLUXDB = os.getenv("USE_INFLUXDB", "false").lower() == "true"

data_manager = DataManager(USE_REDIS, USE_CHROMADB, USE_INFLUXDB)
