import time
from typing import Dict, Any, Optional
from app.core.config import settings

class CrisisCache:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CrisisCache, cls).__new__(cls)
            cls._instance._cache = {}
            cls._instance.ttl_seconds = settings.ADVISOR_CACHE_TTL_SECONDS
            cls._instance.max_size = settings.ADVISOR_CACHE_MAX_SIZE
        return cls._instance

    def _make_key(self, client_id: str, mode: str, temperature: float) -> str:
        return f"{client_id}:{mode}:{temperature}"

    def get(self, client_id: str, mode: str, temperature: float) -> Optional[Dict[str, Any]]:
        key = self._make_key(client_id, mode, temperature)
        if key not in self._cache:
            return None
        
        cached_item = self._cache[key]
        if time.time() - cached_item["cached_at"] > self.ttl_seconds:
            del self._cache[key]
            return None
            
        # Move key to end (LRU)
        val = self._cache.pop(key)
        self._cache[key] = val
        return val["data"]

    def set(self, client_id: str, mode: str, temperature: float, data: Dict[str, Any]):
        key = self._make_key(client_id, mode, temperature)
        if key in self._cache:
            self._cache.pop(key)
            
        self._cache[key] = {
            "data": data,
            "cached_at": time.time()
        }
        
        if len(self._cache) > self.max_size:
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key)

    def invalidate(self, client_id: str):
        keys_to_del = [k for k in self._cache.keys() if k.startswith(f"{client_id}:")]
        for k in keys_to_del:
            self._cache.pop(k, None)

    def clear(self):
        self._cache.clear()

crisis_cache = CrisisCache()
