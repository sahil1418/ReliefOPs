"""Twilio SMS wrapper.

For the demo we build a thin client that returns gracefully when Twilio creds
aren't configured, so the rest of the platform doesn't break in dev. In
production we wire `Twilio Send Message` Firebase extension via Firestore
trigger as a backup path.
"""
from __future__ import annotations

from src.core.config import get_settings
from src.core.logging import get_logger

log = get_logger("relief.sms")


def send_sms(*, to: str, body: str) -> str | None:
    """Returns the Twilio message SID on success, None otherwise."""
    settings = get_settings()
    if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from):
        log.warning("sms.not_configured", to_redacted=to[:6] + "…", body_len=len(body))
        return None

    try:
        from twilio.rest import Client  # local import — lazy
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        msg = client.messages.create(from_=settings.twilio_from, to=to, body=body)
        log.info("sms.sent", sid=msg.sid, to_redacted=to[:6] + "…")
        return msg.sid
    except Exception as exc:  # noqa: BLE001
        log.warning("sms.send_failed", error=str(exc))
        return None
