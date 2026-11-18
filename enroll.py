"""Step 1 - Add an authorised person: capture face samples from the camera.

    python enroll.py --name alice
    python enroll.py --name alice --samples 80
"""
from __future__ import annotations

import argparse
import re
import time

import cv2

from doorlock.config import Settings
from doorlock.recognizer import FaceDetector, prepare_face


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture face samples for one person.")
    parser.add_argument("--name", required=True, help="person's name (letters, digits, _ -)")
    parser.add_argument("--samples", type=int, default=50, help="number of photos to take")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.name):
        parser.error("name may only contain letters, digits, '_' and '-'")

    settings = Settings.from_env()
    out_dir = settings.dataset_dir / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    start = len(list(out_dir.glob("*.jpg")))

    detector = FaceDetector()
    camera = cv2.VideoCapture(settings.camera_index)
    if not camera.isOpened():
        raise SystemExit(f"Cannot open camera {settings.camera_index}")

    print("Look at the camera and slowly turn your head. Press Q to stop.")
    saved, last_save = 0, 0.0
    try:
        while saved < args.samples:
            ok, frame = camera.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            box = detector.largest_face(gray)
            # Space the shots out so the samples differ in pose and expression.
            if box is not None and time.time() - last_save > 0.15:
                cv2.imwrite(str(out_dir / f"{start + saved:04d}.jpg"), prepare_face(gray, box))
                saved += 1
                last_save = time.time()
            if box is not None:
                x, y, w, h = box
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, f"{saved}/{args.samples}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            cv2.imshow("Enroll - press Q to stop", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()

    print(f"Saved {saved} samples to {out_dir}. Now run: python train.py")


if __name__ == "__main__":
    main()
