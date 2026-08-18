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
    # Direct-inventory DB holding the oh_pricing table (Openhouse reference prices
    # by society + area). Read-only; used to price Supply Pipeline units.
    DIRECT_INVENTORY_DB_URL: str = ""
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""
    SHEET_ID: str = ""
    SYNC_INTERVAL_MINUTES: int = 15
    CORS_ORIGINS: str = "http://localhost:5173"
    # extra allowed origins by regex (e.g. Vercel preview deploys: https://.*\.vercel\.app$)
    CORS_ORIGIN_REGEX: str = ""

    # --- runtime / ops ---
    # "dev" | "prod". In prod the app fail-closes on insecure config (see validator below).
    APP_ENV: str = "dev"
    # managed Redis (Upstash / Render KV) for shared cache + rate limit + cron lock.
    # Empty → graceful fallback to in-memory behavior (dev/single-instance).
    REDIS_URL: str = ""
    # emit JSON logs (for log aggregation) instead of the human format
    LOG_JSON: bool = False
    # run the APScheduler cron in this process. Set False on web replicas when the
    # scheduler runs as its own single-instance worker (Redis lock is the backstop).
    RUN_SCHEDULER: bool = True
    # reject request bodies larger than this many bytes (basic DoS guard)
    MAX_BODY_BYTES: int = 1_000_000
    # Leads source spreadsheet (separate from the inventory sheet). Two worksheets:
    # listing portals (99acres/MagicBricks) and Meta.
    LEADS_SHEET_ID: str = "18FTnKh2bwwmMNXZNnxPZsep_ZcDthSFOnCC8zfbQViU"
    LEADS_LISTING_WORKSHEET: str = "Listing Leads_New"
    LEADS_META_WORKSHEET: str = "Meta Affordable_New"
    # Near-real-time poll: the ingest is insert-only + idempotent, so re-running it
    # every couple of minutes is safe and just no-ops when there's nothing new. Tune
    # on Render (1 = fastest) without a redeploy.
    LEADS_SYNC_INTERVAL_MINUTES: int = 2
    # write a "synced" timestamp back to each source row after it lands in our system
    # (needs the service account to have EDITOR access on the leads sheet)
    LEADS_SYNC_WRITEBACK: bool = True
    LEADS_WRITEBACK_COLUMN: str = "DD Synced"
    # Ops visits sheet — one row per Openhouse visit, keyed by the Core visit id.
    # Read-only; drives crm_visits.status (upcoming | completed | cancelled).
    VISITS_SHEET_ID: str = "17eEX021t97pGnJasMJ6v7ERE0jezKEC0S8teKepJRWQ"
    VISITS_WORKSHEET: str = "Sheet1"
    VISITS_SYNC_INTERVAL_MINUTES: int = 30
    # Google Maps key (server-side, for geocoding inventory addresses → lat/lng)
    MAPS_API_KEY: str = ""

    # --- Anthropic (Claude) — powers the on-demand RM performance summaries ---
    # Set on Render to switch the feature on; empty = the endpoint answers 503.
    ANTHROPIC_API_KEY: str = ""
    RM_SUMMARY_MODEL: str = "claude-haiku-4-5-20251001"

    # --- Openhouse Core visit-booking API (server-to-server, X-CRM-Key) ---
    # Base must end in /api/v1/oh/ ; key is shared via Secret Manager. Never sent to the browser.
    CRM_BOOKING_API_BASE_URL: str = ""
    CRM_API_KEY: str = ""

    # --- Gupshup WhatsApp ---
    # Shared secret appended to the callback URL as ?token=... . Empty = no check
    # (fine in dev; set it in prod — the endpoint is public by definition).
    GUPSHUP_WEBHOOK_SECRET: str = ""
    GUPSHUP_API_KEY: str = ""
    # the registered WhatsApp Business number, country code included, digits only
    GUPSHUP_SOURCE_NUMBER: str = ""
    # the Gupshup app name bound to that number — sent as src.name
    GUPSHUP_APP_NAME: str = ""

    # --- Bonvoice PBX (click-to-call) ---
    # Login is exchanged for a token at /usermanagement/external-auth/; set
    # BONVOICE_TOKEN directly to skip that if ops issue a long-lived one.
    BONVOICE_BASE_URL: str = "https://backend.pbx.bonvoice.com"
    BONVOICE_USERNAME: str = ""
    BONVOICE_PASSWORD: str = ""
    BONVOICE_TOKEN: str = ""
    BONVOICE_DID: str = ""             # caller ID the lead sees, e.g. 7946350641
    BONVOICE_CHANNEL_ID: str = "1"     # legA/legB channel id issued with the account
    BONVOICE_WEBHOOK_SECRET: str = ""  # ?token= on the call-log callback URL
    # Scheduled equivalent of the Sync from Bonvoice button. The webhook is the primary
    # path; this is the safety net for dropped callbacks and handset-dialled calls.
    BONVOICE_SYNC_INTERVAL_MINUTES: int = 15
    # Days of history each tick re-pulls. 1 = yesterday+today, so a call at 23:58 is
    # still picked up by the tick after midnight. Re-persisting is a no-op upsert.
    BONVOICE_SYNC_LOOKBACK_DAYS: int = 1

    @property
    def bonvoice_base(self) -> str:
        """Usable base URL, whatever was configured.

        Every Bonvoice endpoint we use — auth, autoCallBridging and callrecords —
        is served by the `backend.` host. The bare host ops hand out
        ("pbx.bonvoice.com") answers nginx 405 for all of them, which surfaced as a
        502 on every click-to-call. So the prefix is derived here rather than trusted
        from config: setting the bare host must not be able to break calling.

        Also normalises a missing scheme, and an env var set to an empty string
        overriding the default (httpx then rejects a path with no scheme)."""
        base = (self.BONVOICE_BASE_URL or "").strip().rstrip("/")
        if not base:
            return "https://backend.pbx.bonvoice.com"
        if not base.startswith(("http://", "https://")):
            base = "https://" + base
        # pbx.bonvoice.com → backend.pbx.bonvoice.com; already-backend hosts and any
        # unrelated host are left alone
        if "//pbx." in base:
            base = base.replace("//pbx.", "//backend.pbx.", 1)
        return base

    @property
    def bonvoice_configured(self) -> bool:
        """Placing a call needs a DID plus some way to authenticate."""
        return bool(self.BONVOICE_DID) and bool(
            self.BONVOICE_TOKEN or (self.BONVOICE_USERNAME and self.BONVOICE_PASSWORD)
        )

    # --- Google OAuth (optional; app stays open until both sides are configured) ---
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    JWT_SECRET: str = "dev-insecure-change-me"
    # a full week — the team lives in this tool all day and a short session logs them
    # out mid-call. Safe to leave long: current_user() re-reads role/active from the
    # users row on every request (30s cache), so a demotion or a deactivation in
    # Settings bites immediately rather than waiting out the token. Only the identity
    # claims (sub/email/name) come from the JWT. Rotate JWT_SECRET, or POST
    # /sessions/logout-all, to force an immediate everyone-out logout.
    JWT_EXPIRY_HOURS: int = 168
    # restrict logins to this email domain ("" = any Google account)
    ALLOWED_EMAIL_DOMAIN: str = "openhouse.in"
    # bootstrap admins — allowed to sign in even before being added, provisioned as
    # admin. Everyone else must be added via Settings first. Comma-separated.
    INITIAL_ADMIN_EMAILS: str = "support@openhouse.in"

    @property
    def initial_admins(self) -> set[str]:
        return {e.strip().lower() for e in self.INITIAL_ADMIN_EMAILS.split(",") if e.strip()}
    # External analytics provider behind /v1/huvo-analytics. Unset = the endpoint
    # reports not_configured rather than failing, so the page can be built first.
    HUVO_ANALYTICS_URL: str = ""
    # Shared secret on the Huvo call-update webhook, sent as ?token= (or X-Huvo-Token).
    # Huvo send unauthenticated by default and issue no token of their own, so this is
    # ours to generate and hand them. Unset = open in dev; in prod the endpoint refuses
    # to serve rather than accept call outcomes for arbitrary numbers.
    HUVO_WEBHOOK_SECRET: str = ""

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
    def direct_inventory_url(self) -> str:
        return normalize_asyncpg_url(self.DIRECT_INVENTORY_DB_URL)

    @property
    def direct_inventory_configured(self) -> bool:
        return bool(self.DIRECT_INVENTORY_DB_URL)

    @property
    def crm_booking_configured(self) -> bool:
        return bool(self.CRM_BOOKING_API_BASE_URL) and bool(self.CRM_API_KEY)

    @property
    def gupshup_send_configured(self) -> bool:
        """Receiving works with no config at all; sending needs all three."""
        return bool(self.GUPSHUP_API_KEY and self.GUPSHUP_SOURCE_NUMBER and self.GUPSHUP_APP_NAME)

    @property
    def redis_configured(self) -> bool:
        return bool(self.REDIS_URL)

    @property
    def is_prod(self) -> bool:
        return self.APP_ENV.strip().lower() in ("prod", "production")

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
    def leads_sheet_configured(self) -> bool:
        return bool(self.LEADS_SHEET_ID) and bool(self.service_account_info)

    @property
    def auth_enabled(self) -> bool:
        """Auth is enforced only once a Google client id is configured — until
        then the API stays open so the live deployment never locks out."""
        return bool(self.GOOGLE_OAUTH_CLIENT_ID)

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

    def assert_prod_safe(self) -> None:
        """Fail-closed: in APP_ENV=prod, raise on insecure config. Called at startup
        (main.py lifespan) so the process aborts before serving. Raises a clean
        RuntimeError listing only the problems — never echoes secret values. Dev/tests
        (APP_ENV unset → 'dev') are unaffected."""
        if not self.is_prod:
            return
        problems = []
        if not self.JWT_SECRET or self.JWT_SECRET == "dev-insecure-change-me" or len(self.JWT_SECRET) < 16:
            problems.append("JWT_SECRET must be a strong secret (>=16 chars), not the default")
        if not self.GOOGLE_OAUTH_CLIENT_ID:
            problems.append("GOOGLE_OAUTH_CLIENT_ID must be set (auth would otherwise be open to anyone)")
        if not self.DATABASE_URL:
            problems.append("DATABASE_URL must be set")
        origins = self.cors_origins
        if not origins or any(any(h in o for h in ("localhost", "127.0.0.1", "0.0.0.0")) for o in origins):
            problems.append("CORS_ORIGINS must be real frontend origin(s), not localhost/empty")
        if problems:
            raise RuntimeError("Refusing to start in APP_ENV=prod:\n  - " + "\n  - ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
