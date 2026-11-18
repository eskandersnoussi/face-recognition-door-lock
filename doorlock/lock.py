"""Door lock backends: the servo motor that moves the latch."""
from __future__ import annotations

import logging
import time

from .config import Settings

log = logging.getLogger(__name__)


class DoorLock:
    def unlock(self) -> None:
        raise NotImplementedError

    def lock(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class SimulatedLock(DoorLock):
    """No hardware: just logs. Lets you run the whole system on a laptop."""

    def __init__(self) -> None:
        self.is_unlocked = False

    def unlock(self) -> None:
        self.is_unlocked = True
        log.info("[LOCK] door UNLOCKED (simulated)")

    def lock(self) -> None:
        self.is_unlocked = False
        log.info("[LOCK] door LOCKED (simulated)")


class ArduinoLock(DoorLock):
    """Servo driven by an Arduino running arduino/door_lock/door_lock.ino.

    Protocol over USB serial: 'U' = unlock, 'L' = lock.
    """

    def __init__(self, port: str, baud: int = 9600) -> None:
        import serial  # pyserial

        self._serial = serial.Serial(port, baud, timeout=1)
        time.sleep(2)  # the Arduino resets when the port opens
        self.lock()

    def unlock(self) -> None:
        self._serial.write(b"U")

    def lock(self) -> None:
        self._serial.write(b"L")

    def close(self) -> None:
        self.lock()
        self._serial.close()


class RaspberryPiLock(DoorLock):
    """Servo wired directly to a Raspberry Pi GPIO pin (PWM)."""

    def __init__(self, pin: int, locked_angle: int, unlocked_angle: int) -> None:
        from gpiozero import AngularServo

        self._locked, self._unlocked = locked_angle, unlocked_angle
        self._servo = AngularServo(
            pin, min_angle=0, max_angle=180,
            min_pulse_width=0.0005, max_pulse_width=0.0025,
        )
        self.lock()

    def unlock(self) -> None:
        self._servo.angle = self._unlocked

    def lock(self) -> None:
        self._servo.angle = self._locked

    def close(self) -> None:
        self.lock()
        time.sleep(0.5)
        self._servo.close()


def create_lock(settings: Settings) -> DoorLock:
    if settings.lock_backend == "arduino":
        return ArduinoLock(settings.serial_port, settings.serial_baud)
    if settings.lock_backend == "raspberrypi":
        return RaspberryPiLock(
            settings.servo_pin, settings.locked_angle, settings.unlocked_angle
        )
    if settings.lock_backend == "simulated":
        return SimulatedLock()
    raise ValueError(f"Unknown LOCK_BACKEND: {settings.lock_backend!r}")
