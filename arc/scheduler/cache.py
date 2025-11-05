from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, MutableMapping, Optional, Tuple


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: float
    updated_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class LRUCache:
    """Simple thread-safe LRU cache with optional TTL support."""

    def __init__(self, max_items: int, *, ttl_seconds: Optional[float] = None) -> None:
        if max_items <= 0:
            raise ValueError("LRUCache max_items must be positive.")
        self._max_items = int(max_items)
        self._ttl = ttl_seconds if ttl_seconds and ttl_seconds > 0 else None
        self._entries: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def keys(self) -> Iterator[str]:
        with self._lock:
            return iter(list(self._entries.keys()))

    def get(self, key: str) -> Optional[Any]:
        entry = self.get_entry(key)
        return entry.value if entry else None

    def get_entry(self, key: str) -> Optional[CacheEntry]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            if self._is_expired(entry):
                self._entries.pop(key, None)
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return entry

    def set(self, key: str, value: Any, *, metadata: Optional[MutableMapping[str, Any]] = None) -> CacheEntry:
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=now,
                    updated_at=now,
                    metadata=dict(metadata or {}),
                )
                self._entries[key] = entry
            else:
                entry.value = value
                entry.updated_at = now
                if metadata:
                    entry.metadata.update(metadata)
            self._entries.move_to_end(key)
            self._evict_if_needed()
            return entry

    def pop(self, key: str, default: Optional[Any] = None) -> Any:
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is None:
                return default
            return entry.value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._hits = 0
            self._misses = 0

    def _evict_if_needed(self) -> None:
        while len(self._entries) > self._max_items:
            self._entries.popitem(last=False)

    def _is_expired(self, entry: CacheEntry) -> bool:
        if self._ttl is None:
            return False
        return (time.time() - entry.updated_at) > self._ttl

    def snapshot(self) -> Tuple[CacheEntry, ...]:
        with self._lock:
            return tuple(self._entries.values())

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            size = len(self._entries)
            return {
                "size": size,
                "capacity": self._max_items,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": float(self._hits / (self._hits + self._misses)) if (self._hits + self._misses) else 0.0,
            }


class FeatureCache(LRUCache):
    """LRU cache with JSONL persistence for scheduler feature vectors."""

    def __init__(
        self,
        max_items: int,
        *,
        ttl_seconds: Optional[float] = None,
        backing_store: Optional[Path] = None,
        version: str = "v1",
    ) -> None:
        super().__init__(max_items, ttl_seconds=ttl_seconds)
        self._backing_store = backing_store
        self._version = version
        if backing_store:
            backing_store.parent.mkdir(parents=True, exist_ok=True)
            if backing_store.exists():
                self._load(backing_store)

    def _load(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    version = payload.get("version")
                    if version != self._version:
                        continue
                    key = payload["key"]
                    value = payload["value"]
                    metadata = payload.get("metadata", {})
                    entry = CacheEntry(
                        key=key,
                        value=value,
                        created_at=payload.get("created_at", time.time()),
                        updated_at=payload.get("updated_at", time.time()),
                        metadata=dict(metadata),
                    )
                    with self._lock:
                        self._entries[key] = entry
                self._evict_if_needed()
        except FileNotFoundError:
            return

    def persist(self) -> None:
        if not self._backing_store:
            return
        snapshot = self.snapshot()
        with self._backing_store.open("w", encoding="utf-8") as handle:
            for entry in snapshot:
                payload = entry.to_dict()
                payload["version"] = self._version
                json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
                handle.write("\n")


class NamespaceCache:
    """LRU-backed cache partitioned by logical namespace with statistics."""

    def __init__(
        self,
        name: str,
        max_items: int,
        *,
        ttl_seconds: Optional[float] = None,
        version: str = "default",
    ) -> None:
        self.name = name
        self._cache = LRUCache(max_items, ttl_seconds=ttl_seconds)
        self._stats: Dict[str, Dict[str, int]] = {}
        self._version = version

    def update_version(self, version: str) -> None:
        if version == self._version:
            return
        self._version = version
        self._cache.clear()
        self._stats.clear()

    def _compose_key(self, namespace: str, key: str) -> str:
        return f"{namespace}@{self._version}:{key}"

    def get(self, namespace: str, key: str) -> Optional[Any]:
        composite = self._compose_key(namespace, key)
        value = self._cache.get(composite)
        entry_stats = self._stats.setdefault(namespace, {"hits": 0, "misses": 0})
        if value is None:
            entry_stats["misses"] += 1
        else:
            entry_stats["hits"] += 1
        return value

    def set(self, namespace: str, key: str, value: Any) -> None:
        composite = self._compose_key(namespace, key)
        self._cache.set(composite, value)

    def invalidate(self, namespace: Optional[str] = None) -> None:
        if namespace is None:
            self._cache.clear()
            self._stats.clear()
            return
        composite_prefix = f"{namespace}@{self._version}:"
        for entry in self._cache.snapshot():
            if entry.key.startswith(composite_prefix):
                self._cache.pop(entry.key)
        self._stats.pop(namespace, None)

    def stats(self) -> Dict[str, Any]:
        base_stats = self._cache.stats()
        namespaced = {
            namespace: {
                "hits": counts.get("hits", 0),
                "misses": counts.get("misses", 0),
                "hit_rate": (
                    counts["hits"] / (counts["hits"] + counts["misses"])
                    if (counts.get("hits", 0) + counts.get("misses", 0))
                    else 0.0
                ),
            }
            for namespace, counts in self._stats.items()
        }
        return {
            "name": self.name,
            "version": self._version,
            "overall": base_stats,
            "namespaces": namespaced,
        }


def configure_feature_cache(config: MutableMapping[str, Any], *, version: Optional[str] = None) -> FeatureCache:
    scheduler_cfg = dict(config.get("scheduler", {}))
    cache_cfg = dict(scheduler_cfg.get("feature_cache", {}))
    max_items = int(cache_cfg.get("max_items", 256))
    ttl_seconds = cache_cfg.get("ttl_seconds")
    ttl_value = float(ttl_seconds) if ttl_seconds is not None else None
    backing_store_value = cache_cfg.get("backing_store")
    backing_path = Path(backing_store_value) if backing_store_value else None
    diagnostics_cfg = dict(scheduler_cfg.get("diagnostics", {}))
    version_token = version or str(diagnostics_cfg.get("fingerprint_salt", "scheduler_v1"))
    return FeatureCache(
        max_items=max_items,
        ttl_seconds=ttl_value,
        backing_store=backing_path,
        version=version_token,
    )
