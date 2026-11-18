"""Tests for the access logic and the owner's web page. No camera or hardware needed."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doorlock.access_requests import APPROVED, DENIED, EXPIRED, PENDING, RequestStore
from doorlock.config import Settings
from doorlock.controller import AccessController, State
from doorlock.lock import SimulatedLock
from doorlock.notifier import Notifier
from doorlock.recognizer import Recognition
from doorlock.server import create_app

FRAME = np.zeros((120, 160, 3), dtype=np.uint8)
BOX = (10, 10, 100, 100)
KNOWN = Recognition(name="alice", distance=40.0, box=BOX)
STRANGER = Recognition(name=None, distance=120.0, box=BOX)


class FakeNotifier(Notifier):
    def __init__(self, fail=False):
        self.alerts, self.fail = [], fail

    def send_alert(self, link, photo_url=None):
        if self.fail:
            raise RuntimeError("SMS provider down")
        self.alerts.append(link)


@pytest.fixture
def rig(tmp_path):
    settings = Settings(
        captures_dir=tmp_path / "captures", log_file=tmp_path / "logs" / "events.csv",
        required_matches=3, max_attempts=3, attempt_seconds=4, retry_pause=2,
        unlock_seconds=5, owner_timeout=60, cooldown_seconds=10,
    )
    lock, notifier, store = SimulatedLock(), FakeNotifier(), RequestStore()
    controller = AccessController(
        settings, lock, notifier, store, link_for=lambda r: f"http://door/r/{r.token}"
    )
    return controller, lock, notifier, store


def feed(controller, recognition, start, seconds, fps=10):
    """Feed the same result for `seconds`; returns the time after the last frame."""
    t = start
    for i in range(int(seconds * fps) + 1):
        t = start + i / fps
        controller.update(recognition, FRAME, now=t)
    return t


def fail_all_attempts(controller, start=0.0):
    t = start
    for _ in range(controller.s.max_attempts):
        t = feed(controller, STRANGER, t, controller.s.attempt_seconds + controller.s.retry_pause) + 0.1
    return t


def test_known_face_unlocks_then_relocks(rig):
    controller, lock, notifier, _ = rig
    for i in range(3):
        controller.update(KNOWN, FRAME, now=i * 0.1)
    assert controller.state is State.UNLOCKED and lock.is_unlocked
    controller.update(None, FRAME, now=6.0)
    assert controller.state is State.IDLE and not lock.is_unlocked
    assert notifier.alerts == []


def test_single_matching_frame_is_not_enough(rig):
    controller, lock, _, _ = rig
    controller.update(KNOWN, FRAME, now=0.0)
    controller.update(STRANGER, FRAME, now=0.1)
    controller.update(KNOWN, FRAME, now=0.2)
    controller.update(KNOWN, FRAME, now=0.3)
    assert not lock.is_unlocked  # the stranger frame reset the streak


def test_stranger_gets_retry_before_owner_is_alerted(rig):
    controller, lock, notifier, _ = rig
    feed(controller, STRANGER, 0.0, 4.0)
    assert controller.state is State.RETRY
    assert controller.failed_attempts == 1
    assert notifier.alerts == [] and not lock.is_unlocked


def test_known_face_on_second_try_unlocks(rig):
    controller, lock, notifier, _ = rig
    t = feed(controller, STRANGER, 0.0, 4.0)
    feed(controller, KNOWN, t + 2.1, 1.0)
    assert lock.is_unlocked and notifier.alerts == []


def test_owner_alerted_after_max_attempts_with_photo(rig):
    controller, lock, notifier, _ = rig
    fail_all_attempts(controller)
    assert controller.state is State.WAITING_OWNER
    assert len(notifier.alerts) == 1 and not lock.is_unlocked
    photos = list(controller.s.captures_dir.glob("visitor_*.jpg"))
    assert len(photos) == 1


def test_owner_approval_unlocks_door(rig):
    controller, lock, notifier, store = rig
    t = fail_all_attempts(controller)
    token = notifier.alerts[0].rsplit("/", 1)[1]
    store.decide(token, approve=True, now=t)
    controller.update(STRANGER, FRAME, now=t + 0.1)
    assert controller.state is State.UNLOCKED and lock.is_unlocked
    controller.update(None, FRAME, now=t + 6)
    assert not lock.is_unlocked


def test_owner_denial_keeps_door_locked(rig):
    controller, lock, notifier, store = rig
    t = fail_all_attempts(controller)
    store.decide(notifier.alerts[0].rsplit("/", 1)[1], approve=False, now=t)
    controller.update(STRANGER, FRAME, now=t + 0.1)
    assert controller.state is State.COOLDOWN and not lock.is_unlocked
    controller.update(None, FRAME, now=t + 11)
    assert controller.state is State.IDLE


def test_request_expires_without_answer(rig):
    controller, lock, notifier, store = rig
    t = fail_all_attempts(controller)
    controller.update(STRANGER, FRAME, now=t + 61)
    assert controller.state is State.COOLDOWN and not lock.is_unlocked
    # A late tap on "Unlock" must not open the door.
    token = notifier.alerts[0].rsplit("/", 1)[1]
    assert store.decide(token, approve=True, now=t + 62).status == EXPIRED


def test_sms_failure_does_not_crash_the_door(tmp_path):
    settings = Settings(captures_dir=tmp_path / "c", log_file=tmp_path / "events.csv")
    controller = AccessController(
        settings, SimulatedLock(), FakeNotifier(fail=True), RequestStore(),
        link_for=lambda r: r.token,
    )
    fail_all_attempts(controller)
    assert controller.state is State.WAITING_OWNER
    assert "alert_failed" in settings.log_file.read_text()


def test_request_can_only_be_answered_once():
    store = RequestStore()
    request = store.create(Path("x.jpg"), now=0, timeout=60)
    assert store.decide(request.token, approve=False, now=1).status == DENIED
    assert store.decide(request.token, approve=True, now=2).status == DENIED


# ---------------------------------------------------------------- web page
@pytest.fixture
def web(tmp_path):
    import time
    photo = tmp_path / "visitor.jpg"
    photo.write_bytes(b"\xff\xd8fakejpeg")
    store = RequestStore()
    request = store.create(photo, now=time.time(), timeout=60)
    return create_app(store).test_client(), store, request


def test_page_shows_photo_and_buttons(web):
    client, _, request = web
    page = client.get(f"/r/{request.token}")
    assert page.status_code == 200 and b"Unlock door" in page.data
    assert client.get(f"/r/{request.token}/photo").data.startswith(b"\xff\xd8")


def test_unlock_button_approves_request(web):
    client, _, request = web
    assert client.post(f"/r/{request.token}/unlock").status_code == 200
    assert request.status == APPROVED


def test_deny_button_denies_request(web):
    client, _, request = web
    client.post(f"/r/{request.token}/deny")
    assert request.status == DENIED


def test_wrong_token_is_rejected(web):
    client, _, request = web
    assert client.get("/r/not-a-real-token").status_code == 404
    assert client.post("/r/not-a-real-token/unlock").status_code == 404
    assert request.status == PENDING


def test_opening_the_link_does_not_unlock(web):
    client, _, request = web
    assert client.get(f"/r/{request.token}/unlock").status_code == 405
    assert request.status == PENDING
