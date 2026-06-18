import logging
import os
import sys
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from configs.base import settings
from backend.app.core.database import ensure_compatibility, Base, engine
from backend.app.models import all_models  # noqa: F401
from backend.app.api.v1.router import api_router
from escalations.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

os.makedirs(settings.FILE_UPLOAD_PATH, exist_ok=True)
os.makedirs(settings.LOG_PATH, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)


def _port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Q2P Platform starting…")
    app.state.db_ready = False
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await ensure_compatibility()
        app.state.db_ready = True
        start_scheduler()
    except Exception as exc:
        logger.error(
            "Database unavailable during startup; continuing without DB bootstrap: %s",
            exc,
            exc_info=True,
        )
    yield
    if getattr(app.state, "db_ready", False):
        stop_scheduler()
    logger.info("Q2P Platform stopped.")


app = FastAPI(
    title="Q2P — Quote-to-Policy Platform",
    description="Enterprise AI-native insurance workflow automation platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    if not _port_is_available(settings.APP_HOST, settings.APP_PORT):
        raise SystemExit(
            f"Port {settings.APP_PORT} is already in use. Stop the existing backend process or set APP_PORT to a free port."
        )

    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
        reload_excludes=["**/uploads/**", "**/chroma_store/**", "**/logs/**"],
        log_level=settings.LOG_LEVEL.lower(),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
# Trigger reload again
