"""Draws the status text and face box on the camera preview."""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from .controller import State
from .recognizer import Recognition

COLORS = {  # BGR
    State.IDLE: (200, 200, 200),
    State.SCANNING: (0, 200, 255),
    State.RETRY: (0, 140, 255),
    State.WAITING_OWNER: (0, 0, 255),
    State.UNLOCKED: (0, 200, 0),
    State.COOLDOWN: (0, 0, 255),
}


def draw_overlay(frame: np.ndarray, state: State, message: str,
                 recognition: Optional[Recognition]) -> np.ndarray:
    color = COLORS[state]
    if recognition is not None:
        x, y, w, h = recognition.box
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        label = recognition.name or "unknown"
        cv2.putText(frame, f"{label} ({recognition.distance:.0f})", (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 44), (0, 0, 0), -1)
    cv2.putText(frame, message, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    return frame
