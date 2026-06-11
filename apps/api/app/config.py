from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"
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

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


settings = Settings()
