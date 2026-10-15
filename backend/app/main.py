from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.db.database import Database


def create_app(
    settings: Settings | None = None,
    ollama_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(config.database_url)
        app.state.database = database
        try:
            async with httpx.AsyncClient(
                base_url=str(config.ollama_base_url).rstrip("/") + "/",
                timeout=config.ollama_health_timeout_seconds,
                transport=ollama_transport,
                trust_env=False,
            ) as client:
                app.state.ollama_client = client
                yield
        finally:
            await database.close()

    app = FastAPI(title=config.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(health_router, prefix="/api/v1")
    return app
