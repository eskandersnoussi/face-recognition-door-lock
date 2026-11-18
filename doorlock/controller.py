"""Access-control state machine: decides when the door opens.

IDLE -> SCANNING -> UNLOCKED                       (face recognised)
                 -> RETRY -> SCANNING ...          (not recognised, tries left)
                 -> WAITING_OWNER -> UNLOCKED      (owner tapped "Unlock")
                                  -> COOLDOWN      (owner denied / no answer)

The controller has no camera or hardware code in it: it receives one
recognition result per frame, so it can be unit-tested without any device.
"""
from __future__ import annotations

import csv
import logging
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from .access_requests import APPROVED, DENIED, EXPIRED, AccessRequest, RequestStore
from .config import Settings
from .lock import DoorLock
from .notifier import Notifier
from .recognizer import Recognition

log = logging.getLogger(__name__)

# How long the face may disappear before the current try is abandoned.
FACE_LOST_SECONDS = 1.5
# With nobody in front of the camera this long, the failed-try counter resets.
ATTEMPTS_RESET_SECONDS = 15.0


class State(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    RETRY = "retry"
    WAITING_OWNER = "waiting_owner"
    UNLOCKED = "unlocked"
    COOLDOWN = "cooldown"


class EventLog:
    """Appends every access event to a CSV file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("timestamp,event,detail\n", encoding="utf-8")

    def write(self, event: str, detail: str = "") -> None:
        with self.path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [datetime.now().isoformat(timespec="seconds"), event, detail]
            )
        log.info("%s %s", event, detail)


class AccessController:
    def __init__(
        self,
        settings: Settings,
        lock: DoorLock,
        notifier: Notifier,
        store: RequestStore,
        link_for: Callable[[AccessRequest], str],
        photo_url_for: Optional[Callable[[AccessRequest], Optional[str]]] = None,
    ) -> None:
        self.s = settings
        self.lock = lock
        self.notifier = notifier
        self.store = store
        self._link_for = link_for
        self._photo_url_for = photo_url_for or (lambda _request: None)
        self.events = EventLog(settings.log_file)

        self.state = State.IDLE
        self.message = "Look at the camera"
        self.failed_attempts = 0
        self._attempt_started = 0.0
        self._last_face_seen = 0.0
        self._match_name: Optional[str] = None
        self._match_count = 0
        self._until = 0.0          # end of the current UNLOCKED / RETRY / COOLDOWN
        self._request: Optional[AccessRequest] = None

    # ------------------------------------------------------------------ API
    def update(self, recognition: Optional[Recognition], frame: np.ndarray,
               now: Optional[float] = None) -> State:
        """Feed one camera frame's result. Call this for every frame."""
        now = time.time() if now is None else now
        if recognition is not None:
            self._last_face_seen = now

        if self.state is State.UNLOCKED:
            if now >= self._until:
                self.lock.lock()
                self.events.write("locked")
                self._to_idle()
        elif self.state is State.WAITING_OWNER:
            self._check_owner_answer(now)
        elif self.state in (State.RETRY, State.COOLDOWN):
            if now >= self._until:
                self._to_idle(keep_attempts=self.state is State.RETRY)
        elif self.state is State.IDLE:
            if recognition is not None:
                self._start_attempt(now)
                self._scan(recognition, frame, now)
            elif (self.failed_attempts
                  and now - self._last_face_seen > ATTEMPTS_RESET_SECONDS):
                self.failed_attempts = 0
        elif self.state is State.SCANNING:
            self._scan(recognition, frame, now)
        return self.state

    # ------------------------------------------------------------ internals
    def _to_idle(self, keep_attempts: bool = False) -> None:
        self.state = State.IDLE
        self.message = "Look at the camera"
        self._request = None
        if not keep_attempts:
            self.failed_attempts = 0

    def _start_attempt(self, now: float) -> None:
        self.state = State.SCANNING
        self._attempt_started = now
        self._match_name, self._match_count = None, 0
        self.message = f"Scanning... (try {self.failed_attempts + 1}/{self.s.max_attempts})"

    def _scan(self, recognition: Optional[Recognition], frame: np.ndarray,
              now: float) -> None:
        if recognition is None:
            if now - self._last_face_seen > FACE_LOST_SECONDS:
                self._to_idle(keep_attempts=True)  # person walked away
            return

        # Require several consecutive frames agreeing on the same person,
        # so a single lucky frame can never open the door.
        if recognition.known and recognition.name == self._match_name:
            self._match_count += 1
        elif recognition.known:
            self._match_name, self._match_count = recognition.name, 1
        else:
            self._match_name, self._match_count = None, 0

        if self._match_count >= self.s.required_matches:
            self._grant(now, "access_granted", self._match_name or "")
            self.message = f"Welcome, {self._match_name}!"
            return

        if now - self._attempt_started >= self.s.attempt_seconds:
            self.failed_attempts += 1
            self.events.write(
                "attempt_failed", f"{self.failed_attempts}/{self.s.max_attempts}"
            )
            if self.failed_attempts >= self.s.max_attempts:
                self._alert_owner(frame, now)
            else:
                self.state = State.RETRY
                self._until = now + self.s.retry_pause
                left = self.s.max_attempts - self.failed_attempts
                self.message = f"Not recognised. Try again ({left} left)"

    def _grant(self, now: float, event: str, detail: str) -> None:
        self.lock.unlock()
        self.events.write(event, detail)
        self.state = State.UNLOCKED
        self._until = now + self.s.unlock_seconds
        self.failed_attempts = 0
        self._request = None

    def _alert_owner(self, frame: np.ndarray, now: float) -> None:
        self.s.captures_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.fromtimestamp(now).strftime("%Y%m%d_%H%M%S")
        photo = self.s.captures_dir / f"visitor_{stamp}.jpg"
        cv2.imwrite(str(photo), frame)

        self._request = self.store.create(photo, now, self.s.owner_timeout)
        self.events.write("owner_alerted", photo.name)
        try:
            self.notifier.send_alert(
                self._link_for(self._request), self._photo_url_for(self._request)
            )
        except Exception:
            # A failed SMS must not crash the door; the photo is still saved.
            log.exception("Could not send the alert to the owner")
            self.events.write("alert_failed", photo.name)
        self.state = State.WAITING_OWNER
        self.message = "Access denied. Owner notified, please wait..."

    def _check_owner_answer(self, now: float) -> None:
        request = self.store.get(self._request.token, now) if self._request else None
        if request is None:
            self._to_idle()
        elif request.status == APPROVED:
            self._grant(now, "owner_approved", request.photo_path.name)
            self.message = "Owner unlocked the door"
        elif request.status in (DENIED, EXPIRED):
            event = "owner_denied" if request.status == DENIED else "request_expired"
            self.events.write(event, request.photo_path.name)
            self.state = State.COOLDOWN
            self._until = now + self.s.cooldown_seconds
            self._request = None
            self.message = ("Access denied by owner" if request.status == DENIED
                            else "No answer from owner")
