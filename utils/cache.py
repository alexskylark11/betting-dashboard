"""JSON file-based caching with TTL."""

import json
import os
import time
import hashlib

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")


def _cache_path(key: str) -> str:
    safe_key = hashlib.md5(key.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{safe_key}.json")


def get_cached(key: str, ttl_seconds: int) -> dict | None:
    """Return cached data if it exists and is within TTL, else None."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            cached = json.load(f)
        if time.time() - cached.get("_cached_at", 0) > ttl_seconds:
            return None
        return cached.get("data")
    except (json.JSONDecodeError, KeyError):
        return None


def set_cached(key: str, data) -> None:
    """Write data to cache with current timestamp."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(key)
    with open(path, "w") as f:
        json.dump({"_cached_at": time.time(), "data": data}, f)
