import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.core.errors import ApiError
from app.routers import (
    auth,
    buckets,
    inventory,
    leads,
    metrics,
    reminders,
    settings as settings_router,
    societies,
    supply,
    users,
    visits,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.SEED_ON_START:
        from app.db import SessionLocal, engine
        from app.models import Base
        from app.seed import seed

        if settings.is_sqlite:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        async with SessionLocal() as session:
            summary = await seed(session)
            log.info("seed on start: %s", summary)

    scheduler = None
    if settings.RUN_SCHEDULER:
        from app.workers.scheduler import build_scheduler

        scheduler = build_scheduler()
        scheduler.start()
        log.info("APScheduler started (tat_sweep / reminders_due / goldmine nightly)")
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="Openhouse Direct Demand API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- error envelope: {detail, fields?} on every non-2xx ----
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        body: dict = {"detail": exc.detail}
        if exc.fields:
            body["fields"] = exc.fields
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
            fields[".".join(loc) or "body"] = err.get("msg", "Invalid value")
        return JSONResponse(status_code=422, content={"detail": "Validation error", "fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})

    for r in (
        auth.router,
        leads.router,
        reminders.router,
        visits.router,
        inventory.router,
        supply.router,
        buckets.router,
        societies.router,
        metrics.router,
        users.router,
        settings_router.router,
    ):
        app.include_router(r, prefix="/v1")

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"status": "ok"}

    return app


app = create_app()
