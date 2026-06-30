"""
Tests for core memory module.
"""
import unittest
import threading
import time
from core.memory import SharedMemory, MemoryEntry, InMemoryStorage


class TestInMemoryStorage(unittest.TestCase):
    def setUp(self):
        self.storage = InMemoryStorage()
    
    def test_store_and_retrieve(self):
        self.storage.store("key1", "value1", agent="test")
        result = self.storage.retrieve("key1")
        self.assertEqual(result, "value1")
    
    def test_update(self):
        self.storage.store("key1", "value1", agent="test")
        self.storage.store("key1", "value2", agent="test")
        result = self.storage.retrieve("key1")
        self.assertEqual(result, "value2")
    
    def test_delete(self):
        self.storage.store("key1", "value1", agent="test")
        self.assertTrue(self.storage.delete("key1"))
        self.assertFalse(self.storage.exists("key1"))
    
    def test_exists(self):
        self.storage.store("key1", "value1", agent="test")
        self.assertTrue(self.storage.exists("key1"))
        self.assertFalse(self.storage.exists("nonexistent"))
    
    def test_ttl_expiration(self):
        self.storage.store("key1", "value1", agent="test", ttl=1)
        time.sleep(1.1)
        result = self.storage.retrieve("key1")
        self.assertIsNone(result)
    
    def test_get_entries_by_agent(self):
        self.storage.store("key1", "v1", agent="agent1")
        self.storage.store("key2", "v2", agent="agent1")
        self.storage.store("key3", "v3", agent="agent2")
        
        entries = self.storage.get_entries_by_agent("agent1")
        self.assertEqual(len(entries), 2)


class TestSharedMemory(unittest.TestCase):
    def setUp(self):
        # Reset singleton
        SharedMemory._instance = None
        self.memory = SharedMemory()
    
    def test_singleton(self):
        memory2 = SharedMemory()
        self.assertIs(self.memory, memory2)
    
    def test_store_get(self):
        self.memory.store("test_key", {"a": 1}, agent="test")
        result = self.memory.get("test_key")
        self.assertEqual(result["a"], 1)
    
    def test_pubsub(self):
        received = []
        
        def callback(msg):
            received.append(msg)
        
        self.memory.subscribe("test_channel", callback)
        self.memory.publish("test_channel", {"data": "test"}, sender="sender1")
        
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["data"], "test")
    
    def test_concurrent_access(self):
        def writer(idx):
            self.memory.store(f"key_{idx}", idx, agent=f"agent_{idx}")
        
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        keys = self.memory.get_all_keys()
        self.assertEqual(len(keys), 100)


if __name__ == "__main__":
    unittest.main()
