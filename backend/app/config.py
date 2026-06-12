"""App settings — every credential is optional so the app boots with an empty .env."""
import json
import os
from functools import lru_cache
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILES = ("../.env", ".env")


def normalize_asyncpg_url(url: str) -> str:
    """Make a Postgres URL safe for SQLAlchemy+asyncpg.

    Neon hands out URLs like postgres://...?sslmode=require&channel_binding=require;
    asyncpg rejects both query params, and SQLAlchemy needs the +asyncpg driver tag.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    parts = urlparse(url)
    params = dict(parse_qsl(parts.query))
    params.pop("channel_binding", None)
    sslmode = params.pop("sslmode", None)
    if sslmode and sslmode != "disable":
        params["ssl"] = "require"
    return urlunparse(parts._replace(query=urlencode(params)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore"
    )

    DATABASE_URL: str = ""
    PROPERTIES_DATABASE_URL: str = ""
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""
    SHEET_ID: str = ""
    SYNC_INTERVAL_MINUTES: int = 15
    CORS_ORIGINS: str = "http://localhost:5173"
    # returns {"homePhoto":[{homeId, images:[...]}]} for ALL homes; joined on the
    # sheet's home_id column during sync
    PHOTOS_API_URL: str = (
        "https://backend-prod-561394753846.asia-south2.run.app/api/v1/oh/get-homes-photo/"
    )

    @property
    def neon_url(self) -> str:
        return normalize_asyncpg_url(self.DATABASE_URL)

    @property
    def properties_url(self) -> str:
        return normalize_asyncpg_url(self.PROPERTIES_DATABASE_URL)

    @property
    def neon_configured(self) -> bool:
        return bool(self.DATABASE_URL)

    @property
    def properties_configured(self) -> bool:
        return bool(self.PROPERTIES_DATABASE_URL)

    @property
    def sheets_configured(self) -> bool:
        return bool(self.SHEET_ID) and bool(self.service_account_info)

    @property
    def service_account_info(self) -> dict | None:
        raw = self.GOOGLE_SERVICE_ACCOUNT_JSON.strip()
        if not raw:
            return None
        if raw.startswith("{"):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        # treat as a file path, relative paths resolved against repo root then backend/
        for base in ("..", "."):
            path = raw if os.path.isabs(raw) else os.path.join(base, raw)
            if os.path.isfile(path):
                try:
                    with open(path) as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    return None
        return None

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
