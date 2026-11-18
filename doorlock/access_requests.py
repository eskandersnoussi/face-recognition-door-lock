"""Pending "let this person in?" requests, shared by the camera loop and the web server."""
from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

PENDING, APPROVED, DENIED, EXPIRED = "pending", "approved", "denied", "expired"


@dataclass
class AccessRequest:
    token: str          # unguessable id used in the link sent to the owner
    photo_path: Path
    created_at: float
    expires_at: float
    status: str = PENDING


class RequestStore:
    """Thread-safe: the camera loop creates requests, the web server answers them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Dict[str, AccessRequest] = {}

    def create(self, photo_path: Path, now: float, timeout: float) -> AccessRequest:
        request = AccessRequest(
            token=secrets.token_urlsafe(24),
            photo_path=Path(photo_path),
            created_at=now,
            expires_at=now + timeout,
        )
        with self._lock:
            self._requests[request.token] = request
        return request

    def get(self, token: str, now: float) -> Optional[AccessRequest]:
        with self._lock:
            request = self._requests.get(token)
            if request and request.status == PENDING and now >= request.expires_at:
                request.status = EXPIRED
            return request

    def decide(self, token: str, approve: bool, now: float) -> Optional[AccessRequest]:
        """Record the owner's answer. A request can only be answered once, before it expires."""
        with self._lock:
            request = self._requests.get(token)
            if request is None:
                return None
            if request.status == PENDING:
                if now >= request.expires_at:
                    request.status = EXPIRED
                else:
                    request.status = APPROVED if approve else DENIED
            return request
