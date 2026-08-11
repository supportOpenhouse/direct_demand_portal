import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .cache import close_redis
from .config import get_settings
from .core.observability import configure_logging, request_id_ctx
from .core.ratelimit import limiter
from .db import dispose_engines, neon_engine
from .models import Base
from .migrations import run_migrations
from .routers import (
    app_settings, auth, bonvoice, dialer, external_analytics, gupshup, health, inventory,
    leads, live_calls, logs, supply, users, visits,
)
from .services.dialer import start_dialer, stop_dialer
from .workers.scheduler import start_scheduler, stop_scheduler

_settings = get_settings()
configure_logging(_settings.LOG_JSON)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.assert_prod_safe()  # fail-closed: abort boot on insecure prod config
    engine = neon_engine()
    if engine is not None:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            await run_migrations(engine)
        except Exception:
            log.exception("Neon DDL init failed — continuing; /v1/health will report it")
    else:
        log.warning("DATABASE_URL not set — inventory cache disabled")

    # ensure the Direct Demand priority column exists on the external properties table
    # (idempotent ADD COLUMN IF NOT EXISTS — safe to run on every instance)
    from .services.supply import ensure_priority_column

    asyncio.create_task(ensure_priority_column())

    # cron + startup syncs run only where RUN_SCHEDULER is on; the Redis lock further
    # ensures a single instance does the work even if several have it enabled.
    if settings.RUN_SCHEDULER:
        from .cache import try_acquire_lock
        from .services.inventory_sync import run_sync
        from .services.leads_sync import run_leads_sync

        async def _locked_startup(name, fn):
            if await try_acquire_lock(name, 120):
                await fn(trigger="startup")
            else:
                log.info("%s startup sync skipped — another instance holds the lock", name)

        asyncio.create_task(_locked_startup("inventory_sync", run_sync))
        asyncio.create_task(_locked_startup("leads_sync", run_leads_sync))
        start_scheduler(settings.SYNC_INTERVAL_MINUTES, settings.LEADS_SYNC_INTERVAL_HOURS)
        # auto-dialer: places the next call the moment a hangup callback frees an RM
        start_dialer()
    else:
        log.info("RUN_SCHEDULER=false — cron + startup syncs disabled on this instance")
        if not settings.redis_configured:
            # The dialer is in another process, so the events that drive Live Calls
            # are published somewhere this instance can't hear. The page still works
            # off its polling fallback; without this the silence looks like a bug.
            log.warning("RUN_SCHEDULER=false and REDIS_URL unset — Live Calls cannot "
                        "receive push events from the dialer process and will fall "
                        "back to polling. Set REDIS_URL to enable the stream.")

    if settings.is_prod and not settings.redis_configured:
        log.warning("APP_ENV=prod but REDIS_URL unset — cache isn't shared and the cron "
                    "lock is disabled across instances (fine only for a single instance)")

    yield
    stop_dialer()
    stop_scheduler()
    await close_redis()
    await dispose_engines()


app = FastAPI(
    title="Direct Demand Portal API",
    version="1.0",
    lifespan=lifespan,
    docs_url=None if _settings.is_prod else "/docs",
    redoc_url=None if _settings.is_prod else "/redoc",
)

# rate limiting (Redis-backed when configured, else in-memory)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware — Starlette runs the LAST-registered outermost. Desired outer→inner:
# CORS → request-id → security-headers → body-limit → rate-limit → gzip → route.
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def _body_size_limit(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _settings.MAX_BODY_BYTES:
        return JSONResponse({"detail": "request body too large"}, status_code=413)
    return await call_next(request)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if _settings.is_prod:  # don't poison local http with HSTS
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return resp


@app.middleware("http")
async def _request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid4().hex
    token = request_id_ctx.set(rid)
    try:
        resp = await call_next(request)
    finally:
        request_id_ctx.reset(token)
    resp.headers["X-Request-ID"] = rid
    return resp


@app.middleware("http")  # outer of request-id so it can read the X-Request-ID it set
async def _audit(request: Request, call_next):
    from time import monotonic

    start = monotonic()
    resp = await call_next(request)
    try:
        from .services.audit import actor_from_request, record, should_log

        if should_log(request.method, request.url.path):
            ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                  or (request.client.host if request.client else None))
            asyncio.create_task(record(
                actor=actor_from_request(request), method=request.method, path=request.url.path,
                status=resp.status_code, duration_ms=int((monotonic() - start) * 1000),
                ip=ip, request_id=resp.headers.get("X-Request-ID"),
            ))
    except Exception:  # noqa: BLE001 — auditing must never affect the response
        pass
    return resp


app.add_middleware(  # registered last → outermost (adds CORS headers even on errors)
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_origin_regex=_settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=False,  # Bearer-token auth, no cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    # X-Dev-User is the local "view as" switch. Listing it here only lets the browser
    # SEND it; current_user still ignores it unless auth is off and APP_ENV isn't prod,
    # and the production frontend bundle has no code that sets it.
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Dev-User"],
)

app.include_router(health.router, prefix="/v1")
app.include_router(auth.router, prefix="/v1")
app.include_router(inventory.router, prefix="/v1")
app.include_router(supply.router, prefix="/v1")
app.include_router(leads.router, prefix="/v1")
app.include_router(users.router, prefix="/v1")
app.include_router(app_settings.router, prefix="/v1")
app.include_router(external_analytics.router, prefix="/v1")
app.include_router(visits.router, prefix="/v1")
app.include_router(logs.router, prefix="/v1")
app.include_router(gupshup.router, prefix="/v1")
app.include_router(bonvoice.router, prefix="/v1")
app.include_router(dialer.router, prefix="/v1")
# same /dialer prefix, but RM-scoped rather than admin-only — mounted after so the
# admin routes keep their place in the table
app.include_router(live_calls.router, prefix="/v1")
