"""Settings, loaded from environment variables (or a .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional
    def load_dotenv(*_args, **_kwargs):
        return False

ROOT = Path(__file__).resolve().parent.parent


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # --- Camera -----------------------------------------------------------
    camera_index: int = 0

    # --- Recognition ------------------------------------------------------
    # LBPH distance: lower = more similar. Faces above the threshold are "unknown".
    match_threshold: float = 65.0
    # Consecutive matching frames needed before the door opens.
    required_matches: int = 5

    # --- Access policy ----------------------------------------------------
    max_attempts: int = 3          # failed tries before the owner is alerted
    attempt_seconds: float = 4.0   # how long one try lasts
    retry_pause: float = 2.0       # pause between tries ("Try again" message)
    unlock_seconds: float = 5.0    # how long the door stays open
    owner_timeout: float = 120.0   # how long to wait for the owner's answer
    cooldown_seconds: float = 10.0  # pause after a denied / expired request

    # --- Lock hardware ----------------------------------------------------
    lock_backend: str = "simulated"   # simulated | arduino | raspberrypi
    serial_port: str = "COM3"         # e.g. COM3 on Windows, /dev/ttyACM0 on Linux
    serial_baud: int = 9600
    servo_pin: int = 18               # BCM pin, Raspberry Pi backend only
    locked_angle: int = 0
    unlocked_angle: int = 90

    # --- Owner notification -----------------------------------------------
    notifier: str = "console"         # console | twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    owner_phone: str = ""
    # Attach the visitor photo to the message (MMS). Needs PUBLIC_BASE_URL,
    # because Twilio downloads the photo from the internet.
    send_mms: bool = False

    # --- Web server (owner's approval page) --------------------------------
    server_host: str = "0.0.0.0"
    server_port: int = 5000
    # Address the owner's phone can reach, e.g. an ngrok URL.
    # Empty = http://<this machine's LAN IP>:<port> (same Wi-Fi only).
    public_base_url: str = ""

    # --- Paths ------------------------------------------------------------
    dataset_dir: Path = ROOT / "dataset"
    model_dir: Path = ROOT / "trainer"
    captures_dir: Path = ROOT / "captures"
    log_file: Path = ROOT / "logs" / "events.csv"

    @property
    def model_path(self) -> Path:
        return self.model_dir / "model.yml"

    @property
    def labels_path(self) -> Path:
        return self.model_dir / "labels.json"

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        load_dotenv(env_file or ROOT / ".env")
        env = os.environ.get
        d = cls()
        return cls(
            camera_index=int(env("CAMERA_INDEX", d.camera_index)),
            match_threshold=float(env("MATCH_THRESHOLD", d.match_threshold)),
            required_matches=int(env("REQUIRED_MATCHES", d.required_matches)),
            max_attempts=int(env("MAX_ATTEMPTS", d.max_attempts)),
            attempt_seconds=float(env("ATTEMPT_SECONDS", d.attempt_seconds)),
            retry_pause=float(env("RETRY_PAUSE", d.retry_pause)),
            unlock_seconds=float(env("UNLOCK_SECONDS", d.unlock_seconds)),
            owner_timeout=float(env("OWNER_TIMEOUT", d.owner_timeout)),
            cooldown_seconds=float(env("COOLDOWN_SECONDS", d.cooldown_seconds)),
            lock_backend=env("LOCK_BACKEND", d.lock_backend).lower(),
            serial_port=env("SERIAL_PORT", d.serial_port),
            serial_baud=int(env("SERIAL_BAUD", d.serial_baud)),
            servo_pin=int(env("SERVO_PIN", d.servo_pin)),
            locked_angle=int(env("LOCKED_ANGLE", d.locked_angle)),
            unlocked_angle=int(env("UNLOCKED_ANGLE", d.unlocked_angle)),
            notifier=env("NOTIFIER", d.notifier).lower(),
            twilio_account_sid=env("TWILIO_ACCOUNT_SID", ""),
            twilio_auth_token=env("TWILIO_AUTH_TOKEN", ""),
            twilio_from=env("TWILIO_FROM", ""),
            owner_phone=env("OWNER_PHONE", ""),
            send_mms=_bool(env("SEND_MMS", "false")),
            server_host=env("SERVER_HOST", d.server_host),
            server_port=int(env("SERVER_PORT", d.server_port)),
            public_base_url=env("PUBLIC_BASE_URL", "").rstrip("/"),
        )
