from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration loaded from environment / .env file.

    Anything that varies between local-emulator, staging, and production lives here
    so call-sites can stay testable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["local", "staging", "production"] = "local"
    gcp_project_id: str = "relief-logistics"
    gcp_region: str = "us-central1"

    cors_origins: str = "http://localhost:3000"
    # Regex matching all Vercel deployments (production, branch previews, PR previews).
    # Defaults to the public ReliefOps Vercel project; override per-env if you fork.
    cors_origin_regex: str = r"https://relief-o-ps-web(-[a-z0-9-]+)?\.vercel\.app"

    # Firebase emulator hosts — when set, Admin SDK clients route to the local emulator.
    firestore_emulator_host: str | None = None
    firebase_auth_emulator_host: str | None = None
    firebase_storage_emulator_host: str | None = None
    firebase_database_emulator_host: str | None = None
    pubsub_emulator_host: str | None = None

    # Secrets — empty in local dev; injected via Secret Manager in production.
    gemini_api_key: str = ""
    google_maps_api_key: str = ""
    firebase_admin_sa_json: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    sendgrid_api_key: str = ""
    openweather_api_key: str = ""
    reliefweb_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def use_emulators(self) -> bool:
        return bool(self.firestore_emulator_host or self.env == "local")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
