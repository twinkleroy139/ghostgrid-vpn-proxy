import time
from typing import Dict, Optional, Tuple


class MemoryCache:
    """
    In-memory LRU-style cache for static assets (CSS, JS, fonts, images).
    Stores: { url: (content_bytes, content_type, expiry_timestamp) }
    """

    def __init__(self, ttl_seconds: int = 300, max_items: int = 250):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._cache: Dict[str, Tuple[bytes, str, float]] = {}

    def get(self, url: str) -> Optional[Tuple[bytes, str]]:
        """Returns cached (bytes, content_type) if present and unexpired."""
        if url in self._cache:
            content, c_type, expiry = self._cache[url]
            if time.time() < expiry:
                return content, c_type
            else:
                del self._cache[url]
        return None

    def set(self, url: str, content: bytes, content_type: str) -> None:
        """Saves response to cache if within reasonable asset size limits (< 5MB)."""
        if len(content) > 5242880:  # Skip caching assets > 5 MB
            return

        if len(self._cache) >= self.max_items:
            # Drop oldest key
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        expiry = time.time() + self.ttl
        self._cache[url] = (content, content_type, expiry)

    def clear(self) -> None:
        """Flushes the cache."""
        self._cache.clear()


asset_cache = MemoryCache()