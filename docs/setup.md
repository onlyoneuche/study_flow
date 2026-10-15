# Setup and configuration

## Native setup

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js **22+** with npm, [Ollama](https://ollama.com/), and `make`. uv installs Python **3.12** if needed. Run commands from the repository root.

```sh
ollama pull qwen2.5:7b-instruct
# If the Ollama app/service is not already running, run in another terminal:
# ollama serve
make setup
make migrate
make seed
make dev
```

Open [StudyFlow](http://localhost:3000). API documentation is at [localhost:8000/docs](http://localhost:8000/docs). `make dev` starts both apps; Ctrl-C stops both. Separate terminals can use `make dev-backend` and `make dev-frontend`.

`make setup` installs locked dependencies and creates `.env` from [.env.example](../.env.example), replacing the placeholder with a random local auth secret. It preserves existing configuration. `make migrate` applies Alembic migrations; the app never creates tables implicitly. Stop the backend before running `make seed` again, then restart and sign in again.

| Setting | Local default / purpose |
| --- | --- |
| `OLLAMA_BASE_URL` | `http://localhost:11434` |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct`; pull a different local model before changing this |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/studyflow.db`, resolved under `backend/` |
| `AUTH_SECRET` | Random secret created by setup; keep private and stable across restarts |
| `FRONTEND_URL` | `http://localhost:3000`; used in invite and console email links |
| `BACKEND_URL` | Server-only `http://127.0.0.1:8000`; Next.js proxies browser `/api/*` and `/ws/*` |
| `CORS_ORIGINS` | JSON array of permitted local origins |
| `FOCUS_TRACKER_ENABLED` | `false`; set `true` and restart the backend to enable the optional per-session camera checkbox |
| `AUTH_TOKEN_LIFETIME_SECONDS` | 3600; email verification/reset links also default to 3600 seconds |

For another browser-facing hostname, update `FRONTEND_URL` and `CORS_ORIGINS`. Keep the API proxy configured with the reachable backend address. The default development API binds to loopback. Device access also needs an appropriate bind address; installation/camera/notification capabilities generally require HTTPS outside localhost.

The stack uses FastAPI, SQLAlchemy/SQLModel, Alembic, SQLite in WAL mode, fastapi-users, APScheduler and WebSockets; Next.js App Router, TypeScript and Tailwind serve the PWA. Fonts and assets are local. Both development and production builds use Webpack.


## Docker option

Install Docker with Compose and run Ollama on the host. Native Python/Node are not needed for this option. If `.env` is absent, copy `.env.example` to `.env`, then replace `AUTH_SECRET` with the output of `openssl rand -hex 48`. Keep an existing `.env`.

```sh
ollama pull qwen2.5:7b-instruct
# ollama serve  # only when the Ollama app/service is not running
# Fresh setup, or stop the existing app before resetting demo data:
docker compose stop frontend backend
docker compose build
docker compose run --rm --no-deps backend python -m app.demo.seed
docker compose up -d
```

Open [localhost:3000](http://localhost:3000). The backend entrypoint applies migrations before either the seed command or normal API startup. Normal startup also ensures the three curated fallback topics exist. To refresh a built demo later:

```sh
docker compose stop frontend backend
docker compose run --rm --no-deps backend python -m app.demo.seed
docker compose up -d
```

Compose stores SQLite in the persistent `studyflow-data` volume, separate from native `backend/data/`. `make docker-up` builds/starts the app; `make docker-down` stops it while retaining the volume. Reset through the seed command rather than deleting the volume. Both images use unprivileged runtime users and expose ports 3000/8000 on localhost. Run either native servers or Compose on those ports at a time.

Compose overrides `DATABASE_URL`, `BACKEND_URL` and Ollama’s address to use the container database, backend service and `http://host.docker.internal:11434`. On Linux, Ollama may need `OLLAMA_HOST` configured to listen on the Docker bridge interface; restrict access to the local Docker network. Useful logs: `docker compose logs -f backend` (including console email links).
