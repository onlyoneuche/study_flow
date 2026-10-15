# Working on StudyFlow

StudyFlow is a social study PWA with solo/live sessions, local AI quizzes, points and squad streaks. The MVP and minimal Focus Tracker are implemented.

## Start here

Read [the design](docs/studyflow-design.md) in full before changing product behaviour. It is the source of truth for rules, data, API and quiz prompts. Follow explicit user decisions; leave a TODO for unresolved rules rather than inventing behaviour.

| When working on… | Read… |
| --- | --- |
| Setup, environment or Docker | [Setup](docs/setup.md), [.env.example](.env.example) |
| Existing user flows | [Usage](docs/usage.md) |
| UI | [Mobile](docs/mockups/mobile.html) and [desktop](docs/mockups/desktop.html) mockups |
| Seed data or presenting | [Demo data](docs/demo-data.md), [demo script](docs/demo.md) |
| Tests | [Testing](docs/testing.md) |
| Camera tracking | [Focus Tracker](docs/focus-tracker.md), design §9.13 |
| Deferred features | [Backlog](docs/backlog.md) |
| Previous decisions | [Implementation notes](docs/implementation-notes.md); test results there are historical |

## Where to find things

| Location | Responsibility |
| --- | --- |
| `backend/app/api/`, `backend/app/auth/` | FastAPI routes, access checks, fastapi-users and console emails |
| `backend/app/services/` | Sessions, presence, completion/scoring, squads, streaks and jobs |
| `backend/app/models/`, `backend/app/db/`, `backend/alembic/` | SQLAlchemy models, SQLite setup and migrations |
| `backend/app/quizzes/`, `backend/app/demo/` | Ollama generation/validation, cached quizzes and safe demo seeding |
| `backend/app/core/` | Configuration, Lagos calendar and shared study helpers |
| `frontend/src/app/`, `frontend/src/components/` | Next.js pages, layouts and UI |
| `frontend/src/lib/`, `frontend/src/workers/` | API clients, focus calculations and MediaPipe worker |
| `backend/tests/`, `frontend/tests/` | Backend tests and Playwright flows |
| `scripts/`, `Makefile` | Setup, development and test runners |

Keep the existing stack: Python 3.12/uv, FastAPI, SQLModel/SQLAlchemy, Alembic, SQLite WAL, fastapi-users, APScheduler, WebSockets; Next.js App Router, TypeScript, Tailwind and Webpack. Use local Ollama (`qwen2.5:7b-instruct` by default, env-configurable). No paid APIs or hosted backends.

## Commands

Run from the repository root. See the setup guide for prerequisites.

| Command | Purpose |
| --- | --- |
| `make setup` | Install locked dependencies and initialise local configuration |
| `make migrate` | Apply Alembic migrations |
| `make seed` | Create/reset only the owned demo fixture; stop the backend first |
| `make dev` | Run both apps on ports 3000/8000 |
| `make test` | Backend lint/format/tests and frontend lint/TypeScript |
| `make build` | Build the production frontend |
| `make migration-check` | Check migrated schema against models |
| `make test-browser` | Responsive Chrome/WebKit checks |
| `make test-demo` | Seeded walkthrough |
| `make test-focus` | Optional tracker checks with mocked/synthetic input |

Browser runners use disposable databases and need ports 3000/8000 free. Run `make test` before code commits, plus the relevant build, migration or browser checks for the changed area. For docs-only edits, validate links, commands and `git diff --check`. Report the checks actually run.

## Changes that need care

- Squads are stored as groups internally. UI copy says **squad**; internal names, routes and JSON still use `group`. Preserve that boundary.
- Reuse the existing services. `points_ledger` is append-only; corrections are adjustment rows. Never compare raw quiz scores across learners or subjects.
- Store timestamps in UTC and use `backend/app/core/calendar.py` for Lagos day/week boundaries. Keep clocks, active time and quiz deadlines on the server.
- Preserve audience-band checks and consent requirements. Keep correct answers private until quiz submission.
- Use Alembic for schema changes. Keep SQLite write transactions short and run LLM work outside them.
- Run one backend worker per database. Preserve the scheduler/seed lock and reset demos through the seed service, keeping non-demo data and history intact.
- Focus Tracker remains opt-in and flag-gated: numeric summaries only, no camera uploads. Scoring, streaks and rankings must never read focus summaries. Extended tracker features remain deferred.
- Follow the mockups and check UI changes at 360, 390, 768 and 1440px. Distinguish WebKit automation from native Safari checks.

Keep README lean and detailed documentation in `docs/`. Update the affected guide when behaviour changes. Keep design/mockup sources tracked; exclude secrets, local databases and generated assets.
