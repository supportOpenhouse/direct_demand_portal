from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Accept Neon/psql-style URLs verbatim: rewrite the scheme for asyncpg and
        # translate libpq-only query params (sslmode, channel_binding) it can't accept.
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        if v.startswith("postgresql+asyncpg://") and "?" in v:
            base, _, query = v.partition("?")
            params = [p for p in query.split("&") if p]
            ssl_required = any(p.startswith("sslmode=") and "disable" not in p for p in params)
            params = [
                p
                for p in params
                if not p.startswith(("sslmode=", "channel_binding=", "ssl="))
            ]
            if ssl_required:
                params.append("ssl=require")
            v = base + ("?" + "&".join(params) if params else "")
        return v
    JWT_SECRET: str = "dev-secret"
    JWT_EXPIRY_HOURS: int = 72
    GOOGLE_CLIENT_ID: str = ""
    CORS_ORIGINS: str = "http://localhost:5173"
    CORS_ORIGIN_REGEX: str | None = None
    TAT_DEFAULT_MINUTES: int = 60
    TAT_WARN_WINDOW_MINUTES: int = 15
    RUN_SCHEDULER: bool = False
    DEV_LOGIN_ENABLED: bool = False
    SEED_ON_START: bool = False
    ENV: str = "dev"

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in ("production", "prod")

    def production_misconfigurations(self) -> list[str]:
        """Settings that must never reach production. Checked at startup."""
        if not self.is_production:
            return []
        problems = []
        if self.DEV_LOGIN_ENABLED:
            problems.append("DEV_LOGIN_ENABLED must be false in production (password-less login!)")
        if self.JWT_SECRET == "dev-secret" or len(self.JWT_SECRET) < 32:
            problems.append("JWT_SECRET must be a random secret of 32+ characters in production")
        if not self.GOOGLE_CLIENT_ID:
            problems.append("GOOGLE_CLIENT_ID is required in production — nobody can log in without it")
        if self.is_sqlite:
            problems.append("DATABASE_URL points at SQLite — production must use Postgres")
        return problems

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


settings = Settings()
