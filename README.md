# StudyFlow

A local, social study app for the hackathon. Python 3.12 + FastAPI + SQLite, Next.js App Router + TypeScript + Tailwind, and local Ollama. No hosted backend or paid API.

**Current milestone: step 7, quiz scoring and points.** Study solo or live, take a validated quiz, see the points breakdown and group bar update, and compare personal improvement within your squad. Streak jobs, the remaining dashboard polish and full demo history arrive in the numbered build order. This is not yet an end-to-end MVP.

The [full design](docs/studyflow-design.md) is the source of truth. UI references: [mobile](docs/mockups/mobile.html), [desktop](docs/mockups/desktop.html). See [implementation notes and TODOs](docs/implementation-notes.md) for unresolved details.

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22+ with npm, and [Ollama](https://ollama.com/). uv downloads Python 3.12 if needed.

```sh
make setup
make migrate
make seed-quizzes
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

Browser checks use installed Google Chrome and Playwright WebKit at 360, 390, 768 and 1440px. Stop the local app servers/containers first; the browser runner creates a disposable `/tmp/studyflow-…` database, applies migrations and seeds fallback quizzes automatically. WebKit provides Safari-engine coverage; an actual Safari/device pass is still required for the completed screens in step 9.

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

Open the invite in another browser/tab. Create an account or sign in; the return destination survives both screens and membership is accepted automatically. Joining reports expired/disabled/exhausted links, full groups, different audience bands and the three-group limit. Existing membership succeeds without consuming another use, even with an old/full invite. The owner can remove a member; each member can leave. Ownership passes to the longest-standing remaining member. Membership history and earned points remain. Groups below three members pause streaks. An empty group is archived with invites disabled; history and ledger remain.

## Sessions demo

Open **Study** for a 25, 45 or 60-minute solo session. Choose a subject and topic; your profile level is saved on the participation. For live sessions, choose a squad and start now or schedule a future start. Other members see the open room under **Study**, join on their own topics, and appear in the members panel. **Study together** on the group page preselects that squad.

The server holds start/end times; countdowns use server time and a monotonic browser timer to correct clock drift. Authenticated WebSockets at `/ws/sessions/{id}?token=JWT` work through the Next.js proxy. Heartbeats run every 15 seconds, even while a tab is hidden. A gap up to 120 seconds counts in full; a longer gap counts 15 seconds. Presence becomes disconnected after 120 seconds without a heartbeat. **Leave session** stops the active clock; **Rejoin session** resumes without counting the break. A solo learner can **Finish early** once 80% active time is saved. Insufficient active time at the end gives no quiz, points or completion.

Live starts run at the server-held scheduled time, even in an empty room. Joining up to 10 minutes late keeps live eligibility and requires 80% of the remaining time. Later arrivals are offered a solo session on the same topic, or can observe the room without live credit. The shared goal includes active members at the scheduled start, including eligible late joiners; people joining the group afterward are excluded. Later departures do not shrink that denominator.

APScheduler checks due session transitions every second and catches up at startup. Use one backend worker for this MVP, because room connections are in memory. Active seconds and the last heartbeat survive restart. Socket access is authenticated and checked again on every event/broadcast; removals cut off access. Query tokens are removed from socket path logs. Supported reactions are a fixed set; no free-text chat is accepted.

Quiz preparation starts in the background. After sufficient study time, choose **Take your quiz**; you can request a browser notification when it is ready. Focus Tracker remains off and uses no camera.

## Quiz demo

Run `make seed-quizzes` for SS2 Chemistry **Mole concept** and **Alkenes**, and Mathematics **Indices**. Docker seeds these automatically. Exact unused cache variants are served first, so those topics work with Ollama offline. Other topics use local Ollama (`OLLAMA_MODEL`, default `qwen2.5:7b-instruct`), validated JSON output and one retry. Generation has a 120-second deadline per try and runs outside database write transactions. Matching queued jobs share one generation.

At your participant end, open the quiz. GET `/participants/{id}/quiz` or POST `/participants/{id}/quiz/start` opens/resumes a single server-timed attempt. Pending work returns 202; insufficient time or an early open returns 409. The effective deadline is the earlier of attempt start + 20 minutes and participant end + 30 minutes. Reloading keeps the timer and local answer draft. Use 1–4 to choose and Enter to advance; answer all 15 before submitting. Correct answers/explanations appear only after submission. Results are personal; they are never used to rank people across subjects.

If generation fails twice, the worker rechecks exact cache, tries related same-subject/level cache with a visible label, then marks the quiz unavailable. Sufficient active time still earns time-only base/live points; missed quiz deadlines follow the same fallback. Flag questions after submission. Three unique-user flags or one inappropriate flag disables the question and retires its variant; every flagged variant is excluded from new cache assignments. Existing results stay unchanged. Retired history is kept, and rerunning the seed does not bypass flags.

## Points and rankings

Successful quiz submission saves base, quiz and personal-improvement ledger lines. Improvement compares your score with your own last three counted quizzes for the same normalised subject and participant-level snapshot; the first quiz earns +3 welcome improvement points. Valid timely quizzes still update your baseline after the daily points cap; unavailable/expired quizzes never do. Rounding uses half up. Ada’s worked example in the design earns 30 live / 25 solo points.

The first three completed sessions per Lagos session day earn points. Later completions save a zero `daily_cap` entry, still count as completed, and remain eligible for streaks and the shared live goal. Base/quiz/improvement credit goes to each of your current groups (up to three); +5 live goes only to the hosting group. The v2 full-group bonus is not awarded. Identical retries return the saved result and cannot create duplicate ledger awards.

Open **Ranks** to see group points per current member (ties use streak), and your selected squad’s improvement-only ranking (ties use completed sessions). Only your audience band appears; individual raw scores are never compared. **Your points history** shows this week’s immutable credits, separately for each group. API routes: `GET /groups/{id}/points?week=YYYY-MM-DD`, `GET /leaderboard/groups?week=…`, `GET /users/me/ledger?from=…&to=…&limit=…&offset=…`. Weeks use Monday dates in Africa/Lagos; all historical rows remain after a reset or departure. Corrections are new adjustment rows, not edits.

## Docker

With Docker running and `.env` created:

```sh
make docker-up  # applies Alembic migrations before starting the API
make docker-down
```

Ollama runs on the host machine. Compose overrides its address to `http://host.docker.internal:11434`; the configured model still comes from `.env`. On Linux, Ollama may need to listen on the Docker bridge interface (`OLLAMA_HOST`); allow access only from your local Docker network. The backend's persistent volume will hold SQLite data. Both app images use unprivileged runtime users. Local ports are 3000 (web) and 8000 (API).

## PWA

The production build includes an install manifest, local app icons and a service worker that caches only a public offline page. Run `npm --prefix frontend run start` after `make build` to exercise installation on localhost, or serve over HTTPS on a device. Development mode does not register a worker. Authenticated API data is never cached by the worker.

## Next milestones

8. Lagos streak/freeze jobs and weekly snapshots.
9. Full responsive screens against the supplied mockups.
10. Study Squad seed history.
11. Complete setup and end-to-end demo instructions.

Only after these work end to end: optional on-device Focus Tracker.
