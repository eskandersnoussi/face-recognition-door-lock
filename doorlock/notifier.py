"""Owner alerts: an SMS with a link to the visitor's photo and Unlock / Deny buttons."""
from __future__ import annotations

import logging
from typing import Optional

from .config import Settings

log = logging.getLogger(__name__)


class Notifier:
    def send_alert(self, link: str, photo_url: Optional[str] = None) -> None:
        raise NotImplementedError


def alert_text(link: str) -> str:
    return (
        "Door alert: an unrecognised person is asking for access. "
        f"See the photo and unlock or deny here: {link}"
    )


class ConsoleNotifier(Notifier):
    """Prints the alert instead of sending it. Useful for testing without Twilio."""

    def send_alert(self, link: str, photo_url: Optional[str] = None) -> None:
        log.warning("[ALERT] %s", alert_text(link))


class TwilioNotifier(Notifier):
    def __init__(self, account_sid: str, auth_token: str, sender: str,
                 owner_phone: str, send_mms: bool = False) -> None:
        missing = [
            name for name, value in [
                ("TWILIO_ACCOUNT_SID", account_sid), ("TWILIO_AUTH_TOKEN", auth_token),
                ("TWILIO_FROM", sender), ("OWNER_PHONE", owner_phone),
            ] if not value
        ]
        if missing:
            raise ValueError("Missing Twilio settings: " + ", ".join(missing))
        from twilio.rest import Client

        self._client = Client(account_sid, auth_token)
        self._from, self._to, self._mms = sender, owner_phone, send_mms

    def send_alert(self, link: str, photo_url: Optional[str] = None) -> None:
        params = {"body": alert_text(link), "from_": self._from, "to": self._to}
        if self._mms and photo_url:
            params["media_url"] = [photo_url]  # photo shown inside the message
        message = self._client.messages.create(**params)
        log.info("SMS sent to owner (sid=%s)", message.sid)


def create_notifier(settings: Settings) -> Notifier:
    if settings.notifier == "twilio":
        return TwilioNotifier(
            settings.twilio_account_sid, settings.twilio_auth_token,
            settings.twilio_from, settings.owner_phone, settings.send_mms,
        )
    if settings.notifier == "console":
        return ConsoleNotifier()
    raise ValueError(f"Unknown NOTIFIER: {settings.notifier!r}")
