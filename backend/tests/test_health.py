import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def config(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        auth_secret="test-secret-with-at-least-32-characters",
        **overrides,
    )


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health_checks_the_configured_ollama_model(path):
    def ollama(request):
        assert str(request.url) == "http://ollama.test:11434/api/tags"
        return httpx.Response(200, json={"models": [{"name": "custom:7b"}]})

    app = create_app(
        config(ollama_base_url="http://ollama.test:11434", ollama_model="custom:7b"),
        httpx.MockTransport(ollama),
    )
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["ollama"]["status"] == "ready"


def test_model_missing_is_degraded_but_api_remains_available():
    app = create_app(
        config(), httpx.MockTransport(lambda _: httpx.Response(200, json={"models": []}))
    )
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["ollama"]["status"] == "model_missing"


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_ollama_connection_failure_does_not_crash_health(failure):
    def ollama(request):
        raise failure("Local dependency unavailable", request=request)

    app = create_app(config(), httpx.MockTransport(ollama))
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["ollama"]["status"] == "unreachable"


@pytest.mark.parametrize("body", [{}, {"models": "invalid"}, {"models": [{}]}])
def test_invalid_ollama_schema_is_reported(body):
    app = create_app(config(), httpx.MockTransport(lambda _: httpx.Response(200, json=body)))
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.json()["ollama"]["status"] == "invalid_response"


def test_invalid_json_is_reported():
    app = create_app(config(), httpx.MockTransport(lambda _: httpx.Response(200, text="not JSON")))
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.json()["ollama"]["status"] == "invalid_response"


def test_ollama_http_error_is_reported():
    app = create_app(config(), httpx.MockTransport(lambda _: httpx.Response(503)))
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.json()["ollama"]["status"] == "unreachable"


def test_default_tag_is_recognised():
    app = create_app(
        config(ollama_model="custom"),
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"models": [{"name": "custom:latest"}]})
        ),
    )
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"


def test_secrets_are_required_and_masked():
    settings = config()
    assert settings.auth_secret.get_secret_value() not in repr(settings)
    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="test", auth_secret="short")


def test_cors_accepts_only_configured_origins():
    app = create_app(
        config(), httpx.MockTransport(lambda _: httpx.Response(200, json={"models": []}))
    )
    with TestClient(app) as client:
        allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
        blocked = client.get("/health", headers={"Origin": "https://untrusted.test"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in blocked.headers
