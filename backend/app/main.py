"""
backend/app/main.py — FastAPI application entry point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.database import engine, Base
from app.middleware.logging_middleware import LoggingMiddleware
from configs.base import BaseConfig

logger = logging.getLogger(__name__)
config = BaseConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Q2P Platform API | env=%s", config.APP_ENV)
    # Initialize DB tables (handled by Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    logger.info("Shutting down Q2P Platform API")
    await engine.dispose()


app = FastAPI(
    title="Q2P Agentic AI Platform",
    description="Enterprise Quote-to-Policy insurance workflow automation platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

# API Router
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": config.APP_NAME, "env": config.APP_ENV}
