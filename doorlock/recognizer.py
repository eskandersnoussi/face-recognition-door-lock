"""Face detection (Haar cascade) and recognition (LBPH) with OpenCV."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

FACE_SIZE = (200, 200)
Box = Tuple[int, int, int, int]  # x, y, w, h


@dataclass
class Recognition:
    """Result for the main face in a frame. name is None for a stranger."""
    name: Optional[str]
    distance: float
    box: Box

    @property
    def known(self) -> bool:
        return self.name is not None


class FaceDetector:
    def __init__(self) -> None:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(path)
        if self._cascade.empty():
            raise RuntimeError(f"Could not load Haar cascade: {path}")

    def largest_face(self, gray: np.ndarray) -> Optional[Box]:
        """Return the biggest face in the image (the person closest to the door)."""
        faces = self._cascade.detectMultiScale(
            gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80)
        )
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        return int(x), int(y), int(w), int(h)


def prepare_face(gray: np.ndarray, box: Box) -> np.ndarray:
    """Crop, resize and normalise lighting so training and live images match."""
    x, y, w, h = box
    face = cv2.resize(gray[y:y + h, x:x + w], FACE_SIZE)
    return cv2.equalizeHist(face)


def _new_lbph():
    if not hasattr(cv2, "face"):
        raise RuntimeError(
            "cv2.face is missing. Install opencv-contrib-python "
            "(and uninstall opencv-python)."
        )
    return cv2.face.LBPHFaceRecognizer_create()


def train(dataset_dir: Path, model_path: Path, labels_path: Path) -> dict:
    """Train LBPH on dataset/<person>/*.jpg. Returns {person: image count}."""
    images, labels, names, counts = [], [], [], {}
    for person_dir in sorted(p for p in Path(dataset_dir).iterdir() if p.is_dir()):
        files = sorted(
            f for f in person_dir.iterdir()
            if f.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        loaded = 0
        for f in files:
            img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            images.append(cv2.resize(img, FACE_SIZE))
            labels.append(len(names))
            loaded += 1
        if loaded:
            names.append(person_dir.name)
            counts[person_dir.name] = loaded
    if not images:
        raise RuntimeError(f"No face images found in {dataset_dir}. Run enroll.py first.")

    model = _new_lbph()
    model.train(images, np.array(labels, dtype=np.int32))
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(model_path))
    labels_path.write_text(json.dumps(names, indent=2), encoding="utf-8")
    return counts


class FaceRecognizer:
    def __init__(self, model_path: Path, labels_path: Path, threshold: float) -> None:
        if not Path(model_path).exists() or not Path(labels_path).exists():
            raise FileNotFoundError(
                "No trained model found. Run enroll.py and then train.py first."
            )
        self.threshold = threshold
        self.detector = FaceDetector()
        self._model = _new_lbph()
        self._model.read(str(model_path))
        self._names = json.loads(Path(labels_path).read_text(encoding="utf-8"))

    def recognize(self, frame: np.ndarray) -> Optional[Recognition]:
        """Return a Recognition for the largest face, or None if no face is visible."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        box = self.detector.largest_face(gray)
        if box is None:
            return None
        label, distance = self._model.predict(prepare_face(gray, box))
        name = self._names[label] if distance <= self.threshold else None
        return Recognition(name=name, distance=float(distance), box=box)
