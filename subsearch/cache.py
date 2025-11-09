import time
from threading import RLock
from typing import Any, Dict, Hashable, Optional, Tuple


class TTLCache:
    """Simple in-memory TTL cache suitable for low-traffic self-hosted usage."""

    def __init__(self, default_ttl: int = 60, maxsize: int = 256):
        self.default_ttl = max(1, default_ttl)
        self.maxsize = maxsize
        self._store: Dict[Hashable, Tuple[Any, float]] = {}
        self._lock = RLock()

    def _now(self) -> float:
        return time.monotonic()

    def _purge_expired(self) -> None:
        now = self._now()
        expired = [key for key, (_, exp) in self._store.items() if exp < now]
        for key in expired:
            self._store.pop(key, None)

    def get(self, key: Hashable) -> Optional[Any]:
        with self._lock:
            data = self._store.get(key)
            if not data:
                return None
            value, expires_at = data
            if expires_at < self._now():
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: Hashable, value: Any, ttl: Optional[int] = None) -> Any:
        ttl = self.default_ttl if ttl is None else max(1, ttl)
        with self._lock:
            if len(self._store) >= self.maxsize:
                self._purge_expired()
                if len(self._store) >= self.maxsize:
                    # Remove the oldest item (FIFO) to keep cache bounded
                    oldest = next(iter(self._store))
                    self._store.pop(oldest, None)
            self._store[key] = (value, self._now() + ttl)
        return value

    def invalidate(self, key: Optional[Hashable] = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)


summary_cache = TTLCache(default_ttl=180, maxsize=16)
search_cache = TTLCache(default_ttl=300, maxsize=512)


def invalidate_all_caches() -> None:
    summary_cache.invalidate()
    search_cache.invalidate()
