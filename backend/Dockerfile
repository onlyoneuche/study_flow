FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
RUN useradd --create-home studyflow && mkdir -p /app/data && chown -R studyflow:studyflow /app
USER studyflow
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
