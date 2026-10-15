# StudyFlow

A local, social study app for the hackathon. Python 3.12 + FastAPI + SQLite, Next.js App Router + TypeScript + Tailwind, and local Ollama. No hosted backend or paid API.

**Current milestone: step 1, application scaffold.** Accounts, groups, sessions, quiz/scoring, streak jobs and demo data arrive in the numbered build order. This is not yet an end-to-end MVP.

The [full design](docs/studyflow-design.md) is the source of truth. UI references: [mobile](docs/mockups/mobile.html), [desktop](docs/mockups/desktop.html). See [implementation notes and TODOs](docs/implementation-notes.md) for unresolved details.

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22+ with npm, and [Ollama](https://ollama.com/). uv downloads Python 3.12 if needed.

```sh
make setup
ollama pull qwen2.5:7b-instruct
ollama serve  # only if the Ollama app/service is not already running
make dev
```

`make setup` installs locked dependencies and creates a private `.env` with a random auth secret. It preserves an existing `.env`. Configuration starts from `.env.example`. Set `OLLAMA_MODEL` to use a different locally installed instruct model. Keep `OLLAMA_BASE_URL=http://localhost:11434` for native development.

Open [StudyFlow](http://localhost:3000), [API docs](http://localhost:8000/docs), or [health](http://localhost:8000/health). The frontend forwards `/api/*` to the local API using the server-only `BACKEND_URL`. API endpoint prefix is `/api/v1`.

Run both development servers with `make dev`, or separately with `make dev-backend` and `make dev-frontend`. Ctrl-C stops both processes. No external fonts, analytics or hosted services are required at runtime.

## Checks

```sh
make test    # backend lint, formatting, tests; frontend lint and TypeScript
make build  # frontend production build
```

Browser checks use installed Google Chrome and Playwright WebKit at 360, 390, 768 and 1440px. WebKit provides Safari-engine coverage; an actual Safari/device pass is still required for the completed screens in step 9.

```sh
cd frontend && npx playwright install webkit && cd ..
make test-browser
```

Health checks call Ollama's `/api/tags` with a bounded timeout and verify the configured model is installed, without generating text. HTTP 200 means the API is alive; JSON `status` is `ok` or `degraded`. Ollama details distinguish `ready`, `model_missing`, `unreachable` and `invalid_response`. A missing quiz service does not prevent startup: cached-quiz fallback is part of step 6. Neither database readiness nor generation quality is asserted by this scaffold health check.

Scoring, streak and invite tests will be introduced with their implementations and must pass before every subsequent commit. There are no domain rules or domain tests yet. Migration and seed commands will be added in steps 2 and 10, respectively.

## Docker

With Docker running and `.env` created:

```sh
make docker-up
make docker-down
```

Ollama runs on the host machine. Compose overrides its address to `http://host.docker.internal:11434`; the configured model still comes from `.env`. On Linux, Ollama may need to listen on the Docker bridge interface (`OLLAMA_HOST`); allow access only from your local Docker network. The backend's persistent volume will hold SQLite data. Both app images use unprivileged runtime users. Local ports are 3000 (web) and 8000 (API).

## PWA

The production build includes an install manifest, local app icons and a service worker that caches only a public offline page. Run `npm --prefix frontend run start` after `make build` to exercise installation on localhost, or serve over HTTPS on a device. Development mode does not register a worker. Authenticated API data is never cached by the worker.

## Next milestones

2. Data model and Alembic, including append-only ledger and focus summary schema.
3. fastapi-users authentication.
4. Groups and invites.
5. Server-timed sessions and WebSocket presence.
6. Validated Ollama quizzes and cached fallback.
7. Scoring and ledger.
8. Lagos streak/freeze jobs and weekly snapshots.
9. Full responsive screens against the supplied mockups.
10. Study Squad seed history.
11. Complete setup and end-to-end demo instructions.

Only after these work end to end: optional on-device Focus Tracker.
