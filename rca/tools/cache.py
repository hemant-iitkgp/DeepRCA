"""On-disk cache for deterministic tool outputs, one folder per case (SPEC 3.6).

Safe under parallel tool calls: a per-key lock avoids computing the same entry twice in one process,
and writes go to a unique temporary file that is atomically renamed.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from rca.paths import CACHE_DIR

# bump when tool logic changes so stale cache entries are not reused
CACHE_VERSION = "v2"

_LOCKS: dict[str, threading.Lock] = {}
_GUARD = threading.Lock()
_MEM: dict[str, Any] = {}


def _key(name: str, args: dict) -> str:
    blob = json.dumps(args, sort_keys=True, default=str)
    return f"{name}-{hashlib.sha1(blob.encode()).hexdigest()[:16]}"


def cached(case_dir_key: str, name: str, args: dict, fn: Callable[[], Any], kind: str = "pkl") -> Any:
    d = Path(CACHE_DIR) / CACHE_VERSION / case_dir_key
    p = d / f"{_key(name, args)}.{kind}"
    k = str(p)
    if k in _MEM:
        return _MEM[k]
    with _GUARD:
        lock = _LOCKS.setdefault(k, threading.Lock())
    with lock:
        if k in _MEM:
            return _MEM[k]
        val = None
        if p.exists():
            try:
                if kind == "json":
                    val = json.loads(p.read_text())
                else:
                    with open(p, "rb") as f:
                        val = pickle.load(f)
            except Exception:
                val = None
        if val is None:
            val = fn()
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / f".{p.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            if kind == "json":
                tmp.write_text(json.dumps(val, default=str))
            else:
                with open(tmp, "wb") as f:
                    pickle.dump(val, f)
            os.replace(tmp, p)
        if len(_MEM) > 64:
            _MEM.clear()
        _MEM[k] = val
        return val
