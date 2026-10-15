# StudyFlow

A local, social study app for the hackathon. Python 3.12 + FastAPI + SQLite, Next.js App Router + TypeScript + Tailwind, and local Ollama. No hosted backend or paid API.

**Current milestone: step 4, groups and invites.** Create an account and an invite-only squad, share a link, join through sign-up/login, manage members and transfer ownership. Sessions, quiz/scoring, streak jobs and demo data arrive in the numbered build order. This is not yet an end-to-end MVP.

The [full design](docs/studyflow-design.md) is the source of truth. UI references: [mobile](docs/mockups/mobile.html), [desktop](docs/mockups/desktop.html). See [implementation notes and TODOs](docs/implementation-notes.md) for unresolved details.

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22+ with npm, and [Ollama](https://ollama.com/). uv downloads Python 3.12 if needed.

```sh
make setup
make migrate
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
make migration-check  # verify the migrated schema matches the models
```

Browser checks use installed Google Chrome and Playwright WebKit at 360, 390, 768 and 1440px. WebKit provides Safari-engine coverage; an actual Safari/device pass is still required for the completed screens in step 9.

```sh
cd frontend && npx playwright install webkit && cd ..
make test-browser
```

Health checks call Ollama's `/api/tags` with a bounded timeout and verify the configured model is installed, without generating text. HTTP 200 means the API is alive; JSON `status` is `ok` or `degraded`. Ollama details distinguish `ready`, `model_missing`, `unreachable` and `invalid_response`. A missing quiz service does not prevent startup: cached-quiz fallback is part of step 6. Neither database readiness nor generation quality is asserted by this scaffold health check.

Tests cover migrations, UTC timestamps, WAL/foreign keys, membership/band constraints, invite storage constraints, append-only ledger enforcement and streak/focus storage invariants. Invite acceptance tests cover every rejection state, idempotency, ownership and concurrent capacity/use limits. Full scoring and streak-job tests arrive with those services. Seed commands arrive in step 10.

## Database and migrations

`make migrate` applies Alembic migrations and is safe to rerun. Relative `DATABASE_URL` paths are always resolved from `backend/`, consistently across the API, scripts and migrations. The default is `backend/data/studyflow.db` (ignored by Git). Connections enable WAL, foreign keys and a 10-second busy timeout. Application timestamps must be timezone-aware; storage and returned values use UTC.

The initial migration creates all 15 design tables, including `focus_summaries` without enabling camera tracking. Database triggers reject ledger updates, deletes and replacements; corrections are appended adjustment rows. They also enforce membership caps, audience bands and the two-freezes-per-week limit. `OTHER` maps to `tertiary` and requires recorded 18+ confirmation. Sign-up collects the required confirmations.

Schema changes use a new Alembic revision, never application-startup `create_all`. After editing models, generate a revision from `backend/` with `uv run alembic revision --autogenerate -m "describe change"`, review it (triggers need manual review), then run `make migrate`, `make migration-check` and `make test` from the repository root. Tests downgrade and re-upgrade disposable databases; never downgrade a database whose history you need to retain.

## Authentication demo

Open [Create account](http://localhost:3000/auth/sign-up). Enter your display name, email, password and level. The audience band is derived from the level: JSS/SS requires guardian consent; university/postgraduate/OTHER requires confirmation that you are 18+. Consent timestamps are set by the server. The guardian checkbox also mentions the optional on-device Focus Tracker, which is not enabled yet.

Verification emails print automatically in the backend console. For Docker, use `docker compose logs -f backend`; with `make dev`, use the server terminal. Open the printed `/auth/verify#token=...` link and tap **Verify email**. You can sign in before verification; no additional verification gate has been added to the design. Your account page can resend the email.

**Forgot password?** on sign-in requests a reset email, also printed in the backend console. Open its `/auth/reset-password#token=...` link and set a new password. Email tokens expire after one hour by default; a successful reset invalidates that reset link. Unknown-email requests return the same response. Tokens appear in URL fragments so they are not sent in page-request URLs. No real emails or external mail services are used.

Set `FRONTEND_URL` to the browser-facing app URL when running on a different host. `AUTH_TOKEN_LIFETIME_SECONDS` and `AUTH_EMAIL_TOKEN_LIFETIME_SECONDS` default to 3600. Passwords use Argon2 hashing and must contain 8–128 characters. Browser bearer tokens are kept in session storage and removed on sign-out; fastapi-users JWTs remain valid until expiry and are not revoked server-side by logout or a password reset.

API routes are under `/api/v1`: `POST /auth/register`, `/auth/jwt/login` (form fields `username` and `password`), `/auth/jwt/logout`, `/auth/request-verify-token`, `/auth/verify`, `/auth/forgot-password`, `/auth/reset-password`; `GET/PATCH /users/me`. Profile updates accept display name and level, plus the appropriate confirmation when crossing audience bands without prior consent. Existing group constraints prevent a cross-band level change. Account deletion is deferred pending the documented anonymisation decision.

The award guard uses `(participant_id, group_id, component)`, equivalent to `(user_id, group_id, session_id, award_type)` because participation is unique per user/session and migration 0002 enforces the ledger-user match. A regression test awards one session to three groups and rejects a duplicate within a group. Freeze buckets are Monday dates derived in Africa/Lagos; their boundary is Sunday 23:00 UTC. The scheduled streak/freeze job remains step 8.

## Groups and invites demo

Open **Squad**, create a group (capacity 3–8), then **Create invite**. Copy the link or use **Share on WhatsApp**. New links expire in exactly 7 days; the owner chooses the use limit. **Regenerate invite** disables older links; **Disable invite** closes the current link. Eight-character codes omit ambiguous characters. Public previews reveal only group name and member count.

Open the invite in another browser/tab. Create an account or sign in; the return destination survives both screens and membership is accepted automatically. Joining reports expired/disabled/exhausted links, full groups, different audience bands and the three-group limit. Existing membership succeeds without consuming another use, even with an old/full invite. The owner can remove a member; each member can leave. Ownership passes to the longest-standing remaining member. Membership history and earned points remain. Groups below three members pause streaks. An empty group is closed to joins pending the documented lifecycle TODO.

## Docker

With Docker running and `.env` created:

```sh
make docker-up
docker compose exec backend alembic upgrade head
make docker-down
```

Ollama runs on the host machine. Compose overrides its address to `http://host.docker.internal:11434`; the configured model still comes from `.env`. On Linux, Ollama may need to listen on the Docker bridge interface (`OLLAMA_HOST`); allow access only from your local Docker network. The backend's persistent volume will hold SQLite data. Both app images use unprivileged runtime users. Local ports are 3000 (web) and 8000 (API).

## PWA

The production build includes an install manifest, local app icons and a service worker that caches only a public offline page. Run `npm --prefix frontend run start` after `make build` to exercise installation on localhost, or serve over HTTPS on a device. Development mode does not register a worker. Authenticated API data is never cached by the worker.

## Next milestones

5. Server-timed sessions and WebSocket presence.
6. Validated Ollama quizzes and cached fallback.
7. Scoring and ledger.
8. Lagos streak/freeze jobs and weekly snapshots.
9. Full responsive screens against the supplied mockups.
10. Study Squad seed history.
11. Complete setup and end-to-end demo instructions.

Only after these work end to end: optional on-device Focus Tracker.
