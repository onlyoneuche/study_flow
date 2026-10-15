# StudyFlow

Study together on your own subjects, take a topic quiz, and grow a shared weekly bar through study time and personal improvement. The hackathon MVP covers sign-up, groups/invites, solo/live sessions, quizzes, points, streaks and rankings. All services run locally; no paid APIs or hosted backend.

The [design](docs/studyflow-design.md) is the source of truth. UI references: [mobile](docs/mockups/mobile.html) and [desktop](docs/mockups/desktop.html). [Implementation notes](docs/implementation-notes.md) record decisions and verification. For presenting, use the [2–3 minute demo script](docs/demo.md).

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

`make setup` installs locked dependencies and creates `.env` from [.env.example](.env.example), replacing the placeholder with a random local auth secret. It preserves existing configuration. `make migrate` applies Alembic migrations; the app never creates tables implicitly. Stop the backend before running `make seed` again, then restart and sign in again.

| Setting | Local default / purpose |
| --- | --- |
| `OLLAMA_BASE_URL` | `http://localhost:11434` |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct`; pull a different local model before changing this |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/studyflow.db`, resolved under `backend/` |
| `AUTH_SECRET` | Random secret created by setup; keep private and stable across restarts |
| `FRONTEND_URL` | `http://localhost:3000`; used in invite and console email links |
| `BACKEND_URL` | Server-only `http://127.0.0.1:8000`; Next.js proxies browser `/api/*` and `/ws/*` |
| `CORS_ORIGINS` | JSON array of permitted local origins |
| `AUTH_TOKEN_LIFETIME_SECONDS` | 3600; email verification/reset links also default to 3600 seconds |

For another browser-facing hostname, update `FRONTEND_URL` and `CORS_ORIGINS`. Keep the API proxy configured with the reachable backend address. The default development API binds to loopback. Device access also needs an appropriate bind address; installation/camera/notification capabilities generally require HTTPS outside localhost.

The stack uses FastAPI, SQLAlchemy/SQLModel, Alembic, SQLite in WAL mode, fastapi-users, APScheduler and WebSockets; Next.js App Router, TypeScript and Tailwind serve the PWA. Fonts and assets are local. Both development and production builds use Webpack.

## Demo data

`make seed` prints credentials, actual weekly totals, the scheduled room and Ada’s prepared quiz URL.

- **Email:** `ada@demo.studyflow.example.com`
- **Password:** `StudyFlow-demo-2026!`

| Study Squad member | Subject |
| --- | --- |
| Ada | Chemistry — Mole concept |
| Tunde | Physics — Forces and motion |
| Zainab | Biology — Cell structure |
| Chidi | Mathematics — Indices |
| Emeka | Economics — Demand |
| Funmi | English — Parts of speech |

Friends use their lowercase names at `demo.studyflow.example.com` and the same password. These are fictional verified **SS2 / secondary-band** accounts with fixture consent. The competing **Lagos Brainiacs** has Ife, Musa and Bisi in the same band.

The seed replays heartbeat, session transition, quiz grading, ledger and streak services. Thirteen evaluated days produce a **12-day streak and one freeze used**, with seven recent days of live/solo history and quiz attempts. Today’s extra study brings the weekly bar near **340/600**: six members × the documented 100-point target. The rival has a competing points-per-member average, and a live session is scheduled tonight (19:00 Lagos, or shortly after seed if later).

Actual points and remaining freezes follow the current Lagos calendar. Sunday history can already exceed 340; very early Monday may not have enough elapsed study time to reach it. A freeze in a previous week does not consume this week’s allowance. The seed always prints actual values.

Ada’s prepared quiz belongs to an **already-studied 25-minute solo session**. Its real 20-minute quiz timer starts at seed time: refresh the seed immediately before presenting. New sessions retain their normal **25/45/60-minute** timers. The [short demo](docs/demo.md) explicitly switches from a newly started live room to this prepared participation.

Reset creates a fresh active demo generation and archives the old accounts/groups, disables their invites and cancels their open rooms. Immutable points and study history remain. An ownership registry prevents claiming other accounts by name/email. Non-demo users, groups, existing quiz variants and flags are preserved. Mixed demo/non-demo membership or session history, transferred ownership, or a reserved email collision makes the entire reset refuse safely. For a repeatable pitch, share/copy the invite without joining a real account to the fixture; use another demo member for live presence. Archived generations intentionally remain in the database.

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

## Using the MVP

**Accounts.** Sign up with email/password and education level. Secondary levels require guardian consent; university/OTHER requires 18+ confirmation. OTHER maps to the adult band. Groups cannot cross bands. Verification and password reset screens print their email links to the backend console; open those links in the same local app. No external mail service is used. Demo accounts are already verified.

**Groups.** Create a group under Squad; the creator owns it. Group capacity is 3–8, each user can belong to at most three groups, and invites expire after seven days with an owner-selected use limit. Copy or share via the prefilled WhatsApp link. Logged-out invitees return after sign-up/login and auto-join. Expired, disabled, exhausted, full and wrong-band states show clear messages; existing membership does not consume another use. Owners can regenerate/disable invites or remove members. Members can leave; ownership transfers to the longest-standing remaining member. Empty groups archive, preserving points/history.

**Study.** Start solo or live on your own subject/topic. Live members can choose different topics. Scheduled rooms start at server time; join within ten minutes for live eligibility, or observe/start solo afterward. Active time must reach 80% of the required duration. Heartbeats run every 15 seconds, including hidden tabs; gaps up to 120 seconds receive full credit, longer gaps receive 15 seconds. Leave/rejoin preserves earned active time without counting the break. Hidden tabs pause only future Focus Tracker sampling; they are never labelled away. The tracker is currently off and no camera is used.

**Quiz.** At session start, background work checks cache and calls local Ollama with the documented prompt and JSON schema. It validates exactly 15 questions, retries once, then uses exact/related same-level cache or time-only completion. Correct indices stay on the server until submission. Quiz time is the earlier of **start + 20 minutes** and **participant end + 30 minutes**; reload does not extend it. On desktop, 1–4 chooses and Enter advances. Allow browser notifications from the room to hear when a quiz is ready. Flag questions after submission; flags never change earned scores.

**Progress.** Results save base, quiz and improvement ledger entries. Improvement compares only with your own same-subject/level history. First-three-completions-per-Lagos-day and up-to-three-group rules apply; the +5 live bonus goes only to the host group. Group rankings use points per current member; in-group rankings use improvement points only. Other people’s raw quiz scores are never shown or compared. The daily goal counts group sessions completed today versus members, so it can exceed the denominator.

**Streaks and weeks.** At 02:00 Africa/Lagos, the previous day is kept if every member eligible at that day’s midnight completed study. A missed positive streak consumes a freeze if available, up to two per Lagos week; otherwise it resets. Fewer than three eligible members pauses the day. Startup catches up every due date, including paused days; before 02:00 it stops at today−2, otherwise today−1. Quiz submission updates points immediately; streaks wait for nightly evaluation. Weekly bars and freeze allowances switch Monday 00:00 Lagos without deleting history. Past weeks come from ledger queries, with no stored MVP snapshots.

API routes are under `/api/v1`; see [OpenAPI](http://localhost:8000/docs) and the [design endpoint list](docs/studyflow-design.md#6-api-endpoints). Examples include `GET /groups/{id}/points?week=YYYY-MM-DD`, `GET /leaderboard/groups?week=YYYY-MM-DD` and `GET /users/me/ledger?from=…&to=…`. A week parameter is the Monday date in Africa/Lagos. Corrections append adjustment rows; ledger entries are never edited/deleted.

## Checks and PWA

```sh
make test             # backend lint/format + tests; frontend lint + TypeScript
make build            # production build with standalone assets
make migration-check  # migrated schema versus models
# Stop app servers/containers before browser checks (ports 3000/8000).
(cd frontend && npx playwright install webkit)
make test-browser     # Chrome + WebKit, 360/390/768/1440px
make test-demo        # seeded pitch, Chrome 390px + WebKit 1440px
```

Google Chrome must be installed for Chrome tests. Browser runners create disposable `/tmp/studyflow-…` databases and migrate them; the seeded demo checks each start with fresh data. Tests cover scoring’s worked example, daily/multi-group caps, all invite acceptance edge cases, streak/freezes/catch-up/idempotency, auth, sessions, quiz retries/timeouts and safe seed resets.

Current verification: **209 backend tests**, backend/frontend checks, production build, migration agreement, repeated native/Docker seed runs, and the seeded end-to-end walkthrough pass. The earlier full responsive suite passed 80 checks. All four widths are covered in Chrome and WebKit. A native Safari desktop visual smoke check passed; full native Safari/device testing at each width remains manual because native input/window automation was intermittent.

For PWA installation, run the production frontend with `make build` then `npm --prefix frontend run start` alongside the backend, or use Docker. The service worker caches only a public offline page. Authenticated data is never cached, and study/quiz actions require connectivity. Development mode does not register the worker. Devices require HTTPS for installation outside localhost.

## Known limitations and backlog

- Run **one backend instance/worker per database**: WebSocket connections live in memory. An OS lock beside SQLite (`.jobs.lock`) prevents duplicate scheduler owners and seed/server overlap; never remove it while the server runs.
- Local generation can take up to 120 seconds per try and depends on hardware/model availability. Health returns HTTP 200 with `ok` or `degraded` and Ollama details; it is a liveness/dependency check, not a generation-quality or database-readiness check. Cached demo topics work with Ollama unavailable. `make seed-quizzes` adds SS2 Chemistry/Mole concept, Chemistry/Alkenes and Mathematics/Indices without the group fixture. Reseeding does not revive flagged variants.
- Email delivery is console-only. Guardian consent is a recorded checkbox; guardian email workflows are v2. This is a local hackathon setup with public fictional demo credentials.
- Browser JWTs use session storage. Sign-out clears the browser token, while an issued token remains valid until expiry; logout/password reset do not revoke it server-side. Reset demo generations are inactive and cannot authenticate.
- **Account anonymisation:** resolve the conflict between tombstoning user IDs and append-only ledger history before exposing account deletion.
- **Focus Tracker:** deferred until explicitly approved. No camera sampling, MediaPipe download or comparison flow is enabled; it will never affect points.
- **Weekly snapshots:** backlog only. MVP historical weeks are derived from the ledger using Lagos boundaries.
- **Nudges and RSVPs:** omitted for MVP; nudges are v2.
- **Full-group live bonus G:** v2; no MVP awards.

Steps 1–11 are complete. Focus Tracker stretch work awaits confirmation.
