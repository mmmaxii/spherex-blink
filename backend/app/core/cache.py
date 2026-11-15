"""Small JSON cache on disk for answers of external services (SIA searches, name lookups, catalogues).

    cached("sia", key, ttl_s, lambda: slow_call())

The disk on Render is temporary: this is only a cache, never the place where something is kept.
"""

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)


def make_key(*parts: Any) -> str:
    """Stable short id for a set of parameters (floats are written with fixed precision)."""
    text = "|".join(f"{p:.6f}" if isinstance(p, float) else str(p) for p in parts)
    return hashlib.sha1(text.encode()).hexdigest()[:20]


def write_json_atomic(path: Path, value: Any) -> None:
    """Write through a temporary file so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    tmp.write_text(json.dumps(value), encoding="utf-8")
    os.replace(tmp, path)


def _path(namespace: str, key: str) -> Path:
    return Path(get_settings().cache_dir) / namespace / f"{key}.json"


def get(namespace: str, key: str, ttl_s: float) -> Any | None:
    path = _path(namespace, key)
    try:
        if time.time() - path.stat().st_mtime > ttl_s:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def put(namespace: str, key: str, value: Any) -> None:
    try:
        write_json_atomic(_path(namespace, key), value)
    except OSError as e:  # a full or read-only disk must not break the request
        log.warning("cache write failed for %s/%s: %s", namespace, key, e)


def cached(namespace: str, key: str, ttl_s: float, compute: Callable[[], Any]) -> Any:
    value = get(namespace, key, ttl_s)
    if value is None:
        value = compute()
        put(namespace, key, value)
    return value
