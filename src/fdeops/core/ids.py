"""Identifiers.

``new_id`` produces time-sortable unique ids (ULID layout: 48-bit ms timestamp + 80 random bits,
Crockford base32). ``stable_id`` produces deterministic ids from content, used wherever
reproducibility matters (case ids, idempotency keys).
"""

import base64
import hashlib
import os
import threading
import time

from fdeops.core.hashing import canonical_json

_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
_lock = threading.Lock()
_last_ms = 0
_last_rand = 0


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_id(prefix: str) -> str:
    """Monotonic within a process: ids created in the same millisecond still sort in order."""
    global _last_ms, _last_rand
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms == _last_ms:
            _last_rand += 1
        else:
            _last_ms = ms
            _last_rand = int.from_bytes(os.urandom(10), "big") >> 1
        rand = _last_rand
    return f"{prefix}_{_encode(ms, 10)}{_encode(rand, 16)}"


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256(canonical_json(list(parts)).encode("utf-8")).digest()
    return f"{prefix}_{base64.b32encode(digest).decode('ascii').lower()[:20]}"
