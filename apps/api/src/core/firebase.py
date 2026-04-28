"""Firebase Admin SDK initialization.

Behavior:
- If `FIRESTORE_EMULATOR_HOST` (or `FIREBASE_AUTH_EMULATOR_HOST`) is set, the SDK
  routes to the local emulator suite — no real credentials needed.
- Otherwise, credentials resolve via `FIREBASE_ADMIN_SA_JSON` (raw JSON) or
  Application Default Credentials (Cloud Run's mounted SA).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import TYPE_CHECKING

import firebase_admin
import google.auth.credentials
from firebase_admin import auth as fb_auth
from firebase_admin import credentials, firestore

from src.core.config import get_settings
from src.core.logging import get_logger

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

log = get_logger("relief.firebase")


class _EmulatorCredentials(credentials.Base):
    """Anonymous credentials adapter used when Firebase emulators are active.

    `firebase_admin.initialize_app()` requires *some* credential — even in emulator
    mode where no real auth happens. This adapter satisfies the contract by
    handing back `google.auth.credentials.AnonymousCredentials()` so downstream
    google-cloud-* clients can instantiate without trying ADC.
    """

    def __init__(self) -> None:
        self._g_credential = google.auth.credentials.AnonymousCredentials()

    def get_credential(self) -> google.auth.credentials.AnonymousCredentials:
        return self._g_credential


def _resolve_credentials() -> credentials.Base | None:
    settings = get_settings()

    # Emulator mode: short-circuit, no creds needed.
    if settings.firestore_emulator_host or settings.firebase_auth_emulator_host:
        # Make sure the env vars are visible to google-cloud libraries spawned later.
        if settings.firestore_emulator_host:
            os.environ.setdefault("FIRESTORE_EMULATOR_HOST", settings.firestore_emulator_host)
        if settings.firebase_auth_emulator_host:
            os.environ.setdefault(
                "FIREBASE_AUTH_EMULATOR_HOST", settings.firebase_auth_emulator_host
            )
        if settings.pubsub_emulator_host:
            os.environ.setdefault("PUBSUB_EMULATOR_HOST", settings.pubsub_emulator_host)
        log.info(
            "firebase.emulator_mode",
            firestore=settings.firestore_emulator_host,
            auth=settings.firebase_auth_emulator_host,
        )
        return _EmulatorCredentials()

    sa_json = settings.firebase_admin_sa_json.strip()
    if sa_json:
        try:
            payload = json.loads(sa_json)
            return credentials.Certificate(payload)
        except json.JSONDecodeError as exc:
            log.warning("firebase.sa_json_invalid", error=str(exc))

    # Fall back to Application Default Credentials.
    return credentials.ApplicationDefault()


@lru_cache(maxsize=1)
def init_firebase() -> firebase_admin.App:
    settings = get_settings()
    if firebase_admin._apps:  # pyright: ignore[reportPrivateUsage]
        return firebase_admin.get_app()
    cred = _resolve_credentials()
    options: dict[str, str] = {"projectId": settings.gcp_project_id}
    app = firebase_admin.initialize_app(cred, options)
    log.info("firebase.initialized", project=settings.gcp_project_id)
    return app


@lru_cache(maxsize=1)
def get_firestore() -> "FirestoreClient":
    init_firebase()
    return firestore.client()


def get_auth() -> "fb_auth":
    init_firebase()
    return fb_auth
