from typing import Literal

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings

router = APIRouter(tags=["health"])


class OllamaModel(BaseModel):
    name: str


class OllamaTags(BaseModel):
    models: list[OllamaModel]


class OllamaHealth(BaseModel):
    status: Literal["ready", "model_missing", "unreachable", "invalid_response"]
    model: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    ollama: OllamaHealth
    # Infrastructure failure must not prevent using cached quizzes (design §3.7).
    version: str = Field(default="0.1.0")


async def check_ollama(settings: Settings, client: httpx.AsyncClient) -> OllamaHealth:
    try:
        response = await client.get("api/tags")
        response.raise_for_status()
        tags = OllamaTags.model_validate(response.json())
    except httpx.HTTPError:
        return OllamaHealth(
            status="unreachable",
            model=settings.ollama_model,
            message="Ollama is unavailable. Start the local Ollama server.",
        )
    except (ValueError, ValidationError):
        return OllamaHealth(
            status="invalid_response",
            model=settings.ollama_model,
            message="Ollama returned an unexpected model list.",
        )

    # Ollama may add :latest to names without an explicit tag.
    requested = settings.ollama_model
    canonical = requested if ":" in requested.rsplit("/", 1)[-1] else f"{requested}:latest"
    available = {model.name for model in tags.models}
    ready = bool({requested, canonical} & available)
    return OllamaHealth(
        status="ready" if ready else "model_missing",
        model=requested,
        message="Local quiz model is available."
        if ready
        else "Pull the configured model in Ollama.",
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    ollama = await check_ollama(settings, request.app.state.ollama_client)
    # This is liveness plus dependency diagnostics, not a strict readiness gate.
    return HealthResponse(
        status="ok" if ollama.status == "ready" else "degraded",
        service=settings.app_name,
        ollama=ollama,
    )
