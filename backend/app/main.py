import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import dispose_engines, neon_engine
from .models import Base
from .routers import health, inventory, supply
from .workers.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = neon_engine()
    if engine is not None:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception:
            log.exception("Neon DDL init failed — continuing; /v1/health will report it")
    else:
        log.warning("DATABASE_URL not set — inventory cache disabled")

    # initial sheet sync: fire-and-forget so boot never blocks on Google
    from .services.inventory_sync import run_sync

    asyncio.create_task(run_sync(trigger="startup"))
    start_scheduler(settings.SYNC_INTERVAL_MINUTES)
    yield
    stop_scheduler()
    await dispose_engines()


app = FastAPI(title="Direct Demand Portal API", version="phase-1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/v1")
app.include_router(inventory.router, prefix="/v1")
app.include_router(supply.router, prefix="/v1")
