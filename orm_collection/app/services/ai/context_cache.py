import time
from typing import Dict, Any, Optional

class ContextCache:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ContextCache, cls).__new__(cls)
            cls._instance._cache = {}
            cls._instance.ttl_seconds = 300  # 5 minutes
        return cls._instance

    def get(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached context for client_id.
        Returns None if not cached or if TTL has expired.
        """
        if client_id not in self._cache:
            return None
        
        cached_item = self._cache[client_id]
        if time.time() - cached_item["cached_at"] > self.ttl_seconds:
            # Expired
            del self._cache[client_id]
            return None
            
        return cached_item["data"]

    def set(self, client_id: str, data: Dict[str, Any]):
        """Caches client context data."""
        self._cache[client_id] = {
            "data": data,
            "cached_at": time.time()
        }

    def invalidate(self, client_id: str):
        """Invalidates/clears cache for client_id."""
        if client_id in self._cache:
            del self._cache[client_id]

    def clear(self):
        """Clears all cached contexts."""
        self._cache.clear()

context_cache = ContextCache()
