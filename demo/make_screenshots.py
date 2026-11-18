"""Generate the demo screenshots in docs/screenshots/ (SIMULATION, no camera needed).

    python demo/make_screenshots.py

The real access controller, overlay and owner web page are used, but the camera
is replaced by an illustrated placeholder figure and the recognition results
are scripted. Every image is labelled as a simulation.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from doorlock.access_requests import RequestStore  # noqa: E402
from doorlock.config import Settings  # noqa: E402
from doorlock.controller import AccessController  # noqa: E402
from doorlock.lock import SimulatedLock  # noqa: E402
from doorlock.notifier import Notifier  # noqa: E402
from doorlock.overlay import draw_overlay  # noqa: E402
from doorlock.recognizer import Recognition  # noqa: E402
from doorlock.server import create_app  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
W, H = 640, 480
BOX = (230, 95, 180, 180)
PORT = 5099
BANNER = "SIMULATION - illustrated placeholder, not a real person"


def placeholder_frame(shirt: tuple) -> np.ndarray:
    """A fake camera frame: a wall, a door frame and a cartoon figure."""
    frame = np.zeros((H, W, 3), np.uint8)
    frame[:] = np.linspace(150, 95, H, dtype=np.uint8)[:, None, None]  # wall
    cv2.rectangle(frame, (40, 20), (140, H), (70, 90, 120), -1)         # door edge
    cv2.ellipse(frame, (320, 470), (170, 190), 0, 180, 360, shirt, -1, cv2.LINE_AA)
    cv2.rectangle(frame, (295, 250), (345, 300), (150, 185, 225), -1)   # neck
    cv2.circle(frame, (320, 185), 78, (160, 195, 235), -1, cv2.LINE_AA)  # head
    cv2.circle(frame, (292, 175), 8, (60, 60, 60), -1, cv2.LINE_AA)
    cv2.circle(frame, (348, 175), 8, (60, 60, 60), -1, cv2.LINE_AA)
    cv2.ellipse(frame, (320, 212), (28, 14), 0, 0, 180, (60, 60, 60), 3, cv2.LINE_AA)
    cv2.rectangle(frame, (0, H - 30), (W, H), (0, 0, 0), -1)
    cv2.putText(frame, BANNER, (10, H - 9), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


class CaptureLink(Notifier):
    link = ""

    def send_alert(self, link, photo_url=None):
        self.link = link


def find_browser():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("msedge"),
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def browser_shot(browser: str, url: str, out: Path, size: str) -> None:
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--user-data-dir={profile}", f"--window-size={size}",
             f"--screenshot={out}", url],
            check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


OVERVIEW = """<!doctype html><meta charset="utf-8">
<style>
 body {{ margin:0; width:1600px; height:1160px; background:#0f172a; color:#f8fafc;
        font-family:'Segoe UI',system-ui,sans-serif; box-sizing:border-box; padding:44px 56px; }}
 h1 {{ margin:0; font-size:54px; }} h2 {{ margin:8px 0 30px; font-weight:400; color:#94a3b8; font-size:26px; }}
 .row {{ display:flex; gap:26px; align-items:flex-start; }}
 .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:22px 26px; flex:1; }}
 figure {{ margin:0; }} img {{ width:100%; border-radius:12px; display:block; border:1px solid #334155; }}
 figcaption {{ font-size:22px; margin-top:8px; color:#e2e8f0; }}
 b {{ color:#38bdf8; }} .phone {{ width:420px; }}
 footer {{ position:absolute; left:56px; bottom:26px; color:#94a3b8; font-size:19px; }}
</style>
<h1>Face Recognition Door Lock</h1>
<h2>Python &middot; OpenCV &middot; Servo motor (Arduino / Raspberry Pi) &middot; SMS alert &middot; Remote unlock</h2>
<div class="row">
 <div class="grid">
  <figure><img src="{d}/01_access_granted.png"><figcaption><b>1.</b> Known face &rarr; servo unlocks the door</figcaption></figure>
  <figure><img src="{d}/02_try_again.png"><figcaption><b>2.</b> Unknown face &rarr; visitor gets another try</figcaption></figure>
  <figure><img src="{d}/03_owner_notified.png"><figcaption><b>3.</b> Tries used up &rarr; photo sent to owner by SMS</figcaption></figure>
  <figure><img src="{d}/05_owner_unlocked.png"><figcaption><b>5.</b> Owner approves &rarr; door opens</figcaption></figure>
 </div>
 <figure class="phone"><img src="{d}/04_owner_phone_page.png"><figcaption><b>4.</b> Owner's phone: Unlock or Deny</figcaption></figure>
</div>
<footer>Simulated demo: the software is real, the camera image is an illustrated placeholder (no real person shown).</footer>
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    settings = Settings(captures_dir=work / "captures", log_file=work / "events.csv")
    notifier, store = CaptureLink(), RequestStore()
    controller = AccessController(
        settings, SimulatedLock(), notifier, store,
        link_for=lambda r: f"http://127.0.0.1:{PORT}/r/{r.token}",
    )
    resident = Recognition("alice", 41.0, BOX)
    stranger = Recognition(None, 118.0, BOX)
    resident_frame, stranger_frame = placeholder_frame((150, 110, 60)), placeholder_frame((70, 70, 160))

    def step(recognition, frame, now):
        controller.update(recognition, frame.copy(), now=now)

    def save(name, recognition, frame):
        shot = draw_overlay(frame.copy(), controller.state, controller.message, recognition)
        cv2.imwrite(str(OUT / name), shot)
        print("saved", name, "-", controller.message)

    # Scene 1: a known person is recognised.
    t = 0.0
    for _ in range(settings.required_matches):
        t += 0.1
        step(resident, resident_frame, t)
    save("01_access_granted.png", resident, resident_frame)
    t += settings.unlock_seconds + 1
    step(None, resident_frame, t)  # door re-locks

    # Scene 2 and 3: a stranger fails every try, the owner is alerted.
    t += 20
    first = True
    while not notifier.link:
        t += 0.1
        step(stranger, stranger_frame, t)
        if first and controller.failed_attempts == 1:
            save("02_try_again.png", stranger, stranger_frame)
            first = False
    save("03_owner_notified.png", stranger, stranger_frame)

    # Scene 4: the owner's page, rendered by the real Flask app.
    app = create_app(store)
    threading.Thread(target=lambda: app.run(port=PORT), daemon=True).start()
    time.sleep(1.5)
    # The page checks expiry against the real clock, so re-time the simulated request.
    request = store.get(notifier.link.rsplit("/", 1)[1], 0)
    request.expires_at = time.time() + 600
    browser = find_browser()
    if browser:
        browser_shot(browser, notifier.link, OUT / "04_owner_phone_page.png", "500,760")
        print("saved 04_owner_phone_page.png")

    # Scene 5: the owner taps Unlock.
    store.decide(request.token, approve=True, now=time.time())
    step(stranger, stranger_frame, t + 1)
    save("05_owner_unlocked.png", stranger, stranger_frame)

    if browser:
        page = work / "overview.html"
        page.write_text(OVERVIEW.format(d=OUT.as_uri()), encoding="utf-8")
        browser_shot(browser, page.as_uri(), OUT / "00_overview.png", "1600,1160")
        print("saved 00_overview.png")
    else:
        print("No Chrome/Edge found: skipped the phone page and overview images.")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
