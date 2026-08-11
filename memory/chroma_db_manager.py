import logging
try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None

import json
from datetime import datetime

logger = logging.getLogger("ChromaDBManager")

class ChromaDBManager:
    def __init__(self, persist_directory="./chroma_db"):
        """
        Initializes the Vector Database (Long-Term Memory).
        Stores and retrieves past trade context (State + Sentiment + Outcome).
        """
        self.enabled = chromadb is not None
        if not self.enabled:
            logger.warning("[ChromaDB] ChromaDB library not found. Running without Long-Term Memory.")
            return
            
        try:
            # Initialize a persistent local SQLite-backed Chroma client
            self.client = chromadb.PersistentClient(path=persist_directory)
            
            # Create or load the trade memory collection
            self.collection = self.client.get_or_create_collection(
                name="trade_memory",
                metadata={"hnsw:space": "cosine"} # Cosine similarity for matching market states
            )
            logger.info("[ChromaDB] Long-Term Memory Initialized successfully.")
        except Exception as e:
            logger.error(f"[ChromaDB] Initialization Failed: {e}")
            self.enabled = False

    def store_trade(self, trade_id: str, state_vector: list, context: dict, outcome: float):
        """
        Saves a completed trade's state and outcome into the memory bank.
        """
        if not self.enabled:
            return
            
        try:
            # We convert the quantitative state into a string to be embedded, 
            # and also store the literal state_vector as embeddings if we had an embedding model.
            # For simplicity, we just store the metadata.
            
            metadata = {
                "timestamp": datetime.now().isoformat(),
                "outcome_pnl": float(outcome),
                "action": context.get("action", "UNKNOWN"),
                "sentiment_modifier": float(context.get("breakdown", {}).get("sentiment_modifier", 0.0))
            }
            
            # Convert state_vector to list of floats for embedding
            embedding = [float(x) for x in state_vector]
            
            self.collection.add(
                ids=[trade_id],
                embeddings=[embedding],
                metadatas=[metadata],
                documents=[json.dumps(context)]
            )
            logger.info(f"[ChromaDB] Stored trade {trade_id} into memory.")
        except Exception as e:
            logger.error(f"[ChromaDB] Failed to store trade: {e}")

    def query_similar_scenarios(self, current_state_vector: list, top_k: int = 3):
        """
        Finds the most mathematically similar historical market conditions.
        Returns a list of past trade outcomes for the Orchestrator to review.
        """
        if not self.enabled:
            return []
            
        try:
            embedding = [float(x) for x in current_state_vector]
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=top_k
            )
            
            past_outcomes = []
            if results and 'metadatas' in results and results['metadatas']:
                for metadata in results['metadatas'][0]:
                    past_outcomes.append(metadata.get('outcome_pnl', 0.0))
            return past_outcomes
        except Exception as e:
            logger.error(f"[ChromaDB] Failed to query memory: {e}")
            return []

if __name__ == "__main__":
    db = ChromaDBManager()
    if db.enabled:
        # Test inserting a dummy trade
        db.store_trade("trade_001", [0.1]*19, {"action": "LONG"}, 0.05)
        print("Test Query:", db.query_similar_scenarios([0.1]*19))
