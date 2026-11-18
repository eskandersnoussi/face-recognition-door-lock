"""Step 3 - Run the door lock.

    python main.py              # with a preview window
    python main.py --headless   # no window (e.g. Raspberry Pi without a screen)
"""
from __future__ import annotations

import argparse
import logging
import socket
import threading

import cv2

from doorlock.access_requests import RequestStore
from doorlock.config import Settings
from doorlock.controller import AccessController
from doorlock.lock import create_lock
from doorlock.notifier import create_notifier
from doorlock.overlay import draw_overlay
from doorlock.recognizer import FaceRecognizer
from doorlock.server import create_app

log = logging.getLogger("doorlock")


def lan_ip() -> str:
    """This machine's address on the local network (no packet is actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Face recognition door lock.")
    parser.add_argument("--headless", action="store_true", help="run without a preview window")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    settings = Settings.from_env()
    base_url = settings.public_base_url or f"http://{lan_ip()}:{settings.server_port}"

    recognizer = FaceRecognizer(
        settings.model_path, settings.labels_path, settings.match_threshold
    )
    store = RequestStore()
    lock = create_lock(settings)
    controller = AccessController(
        settings, lock, create_notifier(settings), store,
        link_for=lambda r: f"{base_url}/r/{r.token}",
        # Twilio can only fetch the photo for an MMS from a public address.
        photo_url_for=lambda r: (
            f"{base_url}/r/{r.token}/photo" if settings.public_base_url else None
        ),
    )

    app = create_app(store)
    threading.Thread(
        target=lambda: app.run(host=settings.server_host, port=settings.server_port),
        daemon=True,
    ).start()
    log.info("Owner approval pages are served at %s", base_url)

    camera = cv2.VideoCapture(settings.camera_index)
    if not camera.isOpened():
        lock.close()
        raise SystemExit(f"Cannot open camera {settings.camera_index}")

    log.info("Door lock running. Press Q in the window (or Ctrl+C) to quit.")
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                log.error("Camera read failed")
                break
            recognition = recognizer.recognize(frame)
            # Pass a clean copy: the snapshot sent to the owner has no overlay on it.
            state = controller.update(recognition, frame.copy())

            if not args.headless:
                draw_overlay(frame, state, controller.message, recognition)
                cv2.imshow("Face Recognition Door Lock", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        camera.release()
        cv2.destroyAllWindows()
        lock.close()  # always leave the door locked


if __name__ == "__main__":
    main()
