# Implementation notes and open questions

The source of truth is [studyflow-design.md](studyflow-design.md). The user's numbered build order takes precedence over the suggested order in section 10. Supplied HTML references are preserved under `mockups/`; no reference PNGs were supplied.

## Scope decisions from the source

- Group full-live bonus `G` is v2 (§1.2 and §10), so the MVP will not award it.
- Session heartbeats continue while a tab is hidden (§3.3). Only Focus Tracker sampling pauses on a hidden tab (§9.3, §9.5). Hidden-tab pauses must never be labelled away. TODO: ensure the later session UI distinguishes tracker pause from server presence.
- Focus Tracker implementation follows steps 1–11; its table belongs in step 2 as requested. Scoring and streak code must never read it.
- Missing Ollama is a degraded dependency, not an API outage (§3.7). `/health` and `/api/v1/health` return HTTP 200 with detailed dependency state; this avoids blocking startup or Docker liveness when cached quizzes can serve the app. This is an infrastructure choice, not a scoring rule.

## Decisions confirmed by the user, 15 Oct 2026

- `OTHER` maps to `tertiary` and requires an explicit 18+ confirmation, recorded in `adult_confirmed_at`. No cross-band groups.
- Always advance `group_streaks.last_evaluated_date`, including paused days. Keep unique group/day records and update the cursor and day atomically in step 8.
- Latest due day is Lagos today minus two before 02:00, otherwise today minus one. Catch up only through that day in step 8.
- Enforce both quiz deadlines in step 6: `min(quiz_start + 20 min, participant_end + 30 min)`. A late submission is rejected clearly but sufficient active time still earns time-only completion and base points.
- Keep the level snapshot on `session_participants`, with no session-level column.
- Keep the daily goal card based on completed group sessions today versus member count. Omit RSVPs and MVP nudges, and remove cross-person raw-score badges. Rank group members only by improvement points.

These decisions are incorporated into the design document. Their service/UI implementations remain in the relevant numbered build steps.

## Remaining TODO

- Account deletion (§8) says ledger `user_id` is replaced by a tombstone, while §5 forbids any ledger updates. The schema enforces append-only rows and restrictive foreign keys. Resolve the anonymisation strategy before exposing account deletion; do not silently add an exception to ledger immutability.

## Step 1

- Scaffold FastAPI/Python 3.12 with uv, the required stack dependencies and health/configuration tests.
- Scaffold Next.js App Router/TypeScript/Tailwind with responsive navigation, shared design colours, PWA manifest and a public-only offline fallback.
- Add shared environment configuration, local scripts, Docker definitions and locked dependencies.
- Application screens and domain behavior are intentionally scheduled for subsequent steps. The scaffold contains no invented scores, streaks or demo participants.
- Webpack is selected explicitly for development and builds because Turbopack's CSS worker cannot bind its internal port in the execution sandbox.

### Verification

- `make setup`: passed, preserving the existing local `.env`.
- `make test`: 13 backend tests passed; backend formatting/lint and frontend lint/TypeScript passed. The current Starlette test client emits an upstream httpx deprecation warning.
- `make build`: passed, including standalone asset preparation.
- `npm run test:browser`: 16 checks passed against the standalone production server in installed Google Chrome and Playwright WebKit, at 360, 390, 768 and 1440px. Checks cover the real backend proxy, status refresh, navigation, tap sizes, horizontal overflow, manifest/icons and offline recovery. Actual Safari/device verification remains for step 9.
- Ollama is not running on this machine. The real health check reports `degraded`/`unreachable`; model-ready, missing-model and invalid-response behavior is covered with a mocked Ollama transport.
- Public Docker image downloads initially stalled in the desktop credential helper. Validation uses a separate temporary Docker configuration; the user's saved Docker configuration is unchanged.
- Both Docker images built successfully. Compose startup passed, and the container frontend's `/api/v1/health` proxy reaches the container backend. The stack is available locally on ports 3000 and 8000.

### Dependency notes

The installed Next.js lint configuration pulls in `braces` via `fast-glob`/`micromatch`. The registry audit reports five transitive/development advisories rooted in the same `braces` stack-exhaustion issue; the latest published `braces` remains 3.0.3 with no patched version available. These tools process repository files at lint time. The production-only npm audit reports zero advisories. The user accepted deferring this advisory; do not force a framework downgrade.

## Step 2

- Implemented all 15 SQLAlchemy tables with integer IDs, UTC creation timestamps and the documented enums, checks, foreign keys and lookup indexes. `User` extends the integer-ID fastapi-users SQLAlchemy base.
- Added the initial Alembic migration, stable database path resolution, async session dependency, WAL/foreign-key setup, `make migrate` and `make migration-check`. Schema creation is explicit through migrations, never startup `create_all`.
- Added database guards for append-only ledger history (including `INSERT OR REPLACE`), duplicate non-adjustment awards, active membership uniqueness/caps, audience bands and the weekly freeze cap.
- Added supporting storage fields: adult confirmation timestamp; participant `quiz_id` to preserve assigned quizzes before opening; participant `ended_at` for early-finish deadlines; question difficulty from the required quiz schema. Attempt results stay null until submission, preserving the server-held quiz start time.
- Focus summary storage enforces opt-out privacy and metric ranges. Camera processing, coverage validation and comparison endpoints remain stretch work. Scoring and streak calculations are not implemented in this step.

### Verification

- `make test`: 49 backend tests passed, plus backend lint/format and frontend lint/TypeScript. The existing upstream Starlette test-client deprecation warning remains.
- `make migrate`: applied to the native SQLite database and repeated successfully. `make migration-check` reports no schema changes.
- Migration tests cover a deliberately interrupted first migration (DDL rolls back fully), populated downgrade/re-upgrade, and schema/metadata agreement. SQLite uses explicit transactions for atomic migration DDL.
- The backend Docker image builds with the migration files. The migration and schema check pass against the persistent Docker volume; the updated backend starts successfully.

Implementation references: [SQLAlchemy SQLite transactions and foreign keys](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html), [Alembic asyncio integration](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic), [fastapi-users SQLAlchemy adapter](https://fastapi-users.github.io/fastapi-users/latest/configuration/databases/sqlalchemy/).

Technical references: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation), [Next.js PWA guide](https://nextjs.org/docs/app/guides/progressive-web-apps), [Ollama model-list API](https://docs.ollama.com/api/tags).
