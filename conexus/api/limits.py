"""Request guards: per-client rate limits and bounded uploads.

The rate limiter is in memory, which matches the supported deployment (one web process).
Running several workers would need a shared store (e.g. Postgres or Redis) instead.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, UploadFile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB is far above any real contract
# first bytes of each accepted format; .txt / .md must decode as text
MAGIC = {".pdf": (b"%PDF",), ".docx": (b"PK\x03\x04",)}


def client_ip(request: Request) -> str:
    """Render and most hosts put the real client first in X-Forwarded-For."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_s: float) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                retry = int(window_s - (now - q[0])) + 1
                raise HTTPException(429, "Too many attempts. Please wait a moment and try again.",
                                    headers={"Retry-After": str(retry)})
            q.append(now)

    def guard(self, name: str, limit: int, window_s: float):
        """FastAPI dependency: at most `limit` calls per client IP per window for this route."""
        def dep(request: Request) -> None:
            self.check(f"{name}:{client_ip(request)}", limit, window_s)
        return dep


def read_upload(file: UploadFile, suffix: str, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    """Read at most max_bytes (never the whole stream first) and check the file is what it claims to be."""
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"File too large (max {max_bytes // (1024 * 1024)} MB)")
    if not data.strip():
        raise HTTPException(400, "The file is empty")
    if suffix in MAGIC and not data.startswith(MAGIC[suffix]):
        raise HTTPException(415, f"This does not look like a real {suffix} file")
    if suffix in (".txt", ".md"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(415, "Text files must be UTF-8") from None
    return data
