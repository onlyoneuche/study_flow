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

## Step 3

- Confirmed award identity: `(participant_id, group_id, component)` represents `(user_id, group_id, session_id, award_type)`, because each participation is unique per user/session. Migration 0002 rejects a mismatched ledger user. The regression test credits one participation to three groups and rejects a repeat component in the same group; adjustments remain appendable.
- Added shared Lagos date/week and latest-due-day helpers. Regression tests cover Monday 00:00 Lagos (Sunday 23:00 UTC), independent freeze buckets, and the 02:00 catch-up boundary. Step 8 will use these helpers for jobs; there is no UTC-based reset.
- Added fastapi-users bearer JWT authentication, verification and password reset, console email delivery, and private profile read/update routes. No admin/user-list or deletion routes are exposed. Expired/reused email links are rejected, and response validation errors omit inputs to avoid echoing credentials.
- Sign-up derives the audience band from the level and checks the submitted band. Every tertiary level requires 18+ confirmation, every secondary level requires guardian consent including mention of the optional device-only camera feature. Confirmation timestamps come from the server. Profile band changes require any missing confirmation and must satisfy existing group constraints.
- Added responsive sign-up/sign-in, verification/reset, account/profile and sign-out screens, styled with the existing mockup tokens. Browser tokens use session storage; logout clears local credentials. JWT revocation remains the standard fastapi-users stateless behavior (valid until expiry).
- Infrastructure choices: passwords 8–128 characters, Argon2 hashing, one-hour configurable access/email tokens, email links use URL fragments, console delivery only. Verification is available without adding an undocumented sign-in gate.
- Concurrent browser sign-ups exposed SQLite's stale-read-snapshot upgrade failure. Mutating HTTP requests now reserve write intent with `BEGIN IMMEDIATE` before their first database read; read requests keep ordinary transactions. A four-way simultaneous registration regression test covers the fix. Keep future write transactions short and run LLM work outside them.

Auth references: [fastapi-users UserManager](https://fastapi-users.github.io/fastapi-users/latest/configuration/user-manager/), [JWT strategy](https://fastapi-users.github.io/fastapi-users/latest/configuration/authentication/strategies/jwt/).

### Verification

- `make test`: 84 backend tests passed, plus backend lint/format and frontend lint/TypeScript. Coverage includes every education level, missing/forged consent, Argon2 storage, duplicate email, bearer login/profile/logout, console email tokens, expired/reused verification/reset links, protected profile updates and four concurrent registrations.
- Award/freeze regression tests confirm three-group crediting, rejection of mismatched ledger users, Monday 00:00 Lagos buckets and the 02:00 catch-up boundary. Migration checks and round-trip tests pass at revision 0002.
- Production frontend and both Docker images build successfully. All 40 Chrome/WebKit checks pass at 360, 390, 768 and 1440px against an isolated temporary database, covering registration, consent, login persistence, profile edits, logout, reset requests, invalid links, safe return URLs, tap sizes, navigation and PWA/offline behavior. WebKit's native select needed explicit styling for a 48px tap target. Actual Safari/device verification remains for step 9.

Technical references: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation), [Next.js PWA guide](https://nextjs.org/docs/app/guides/progressive-web-apps), [Ollama model-list API](https://docs.ollama.com/api/tags).

## Step 4

Groups and invites use the approved schema without a new migration. Invite codes are eight unambiguous uppercase characters. Existing membership is an idempotent success without consuming an invite use. New acceptance and invite regeneration are serialised with SQLite write intent. Public previews expose only name/count.

Resolved in step 6: the user confirmed that the empty group is archived with invites disabled and history retained. Account anonymisation remains in the backlog.

Verification: 96 backend tests, lint/format, frontend lint/TypeScript, production build and schema check pass. All 48 browser checks pass in Chrome/WebKit at 360, 390, 768 and 1440px, including invite signup/login auto-join and owner removal. Actual Safari/device verification remains for step 9.

## Step 5

Implemented SOLO and scheduled/immediate LIVE creation, per-participant subject/topic/level snapshots, server-held times, private session state and open-session listing. Runtime transitions use APScheduler at one-second intervals with startup catch-up. No schema change is needed. One backend worker is required while room connections remain in memory.

WebSocket heartbeat accounting uses the documented 120-second grace and 15-second long-gap credit. Whole-second timestamp differences preserve fractional carry between consecutive heartbeats without a new schema field. Duplicate connections share the same persisted heartbeat cursor and cannot double-credit time. An explicit Leave acts as the last presence observation and then stops accumulation; rejoin resets the cursor and preserves the original snapshot. Session end itself does not invent a heartbeat or unobserved tail credit. SOLO early finish requires 80% active time and saves participant end for the later quiz deadline. Insufficient time is incomplete. Quiz/ledger completion remains for steps 6/7.

Late LIVE joins through exactly 10 minutes retain live eligibility and require 80% of remaining time. Later arrivals have no live participation or shared-goal credit; the UI offers SOLO on the same topic, or the member can observe through the socket. Sockets recheck active account/membership and accept only a fixed reaction set. Query credentials are stripped before socket path logging. Hidden tabs keep presence heartbeats; only future tracker sampling pauses, never an away label. Focus Tracker remains off.

Resolved in step 6: the user defined the shared-goal denominator as active group members at the scheduled start. The current goal uses membership intervals at that timestamp; new group arrivals are excluded, qualifying late participants count, and later departures do not shrink the denominator. The v2 full-group bonus remains deferred.

Step 6 integration point: enqueue quiz preparation after participant creation/commit and at a scheduled start, outside SQLite write transactions. Until implemented, quiz status remains pending; sufficient time alone does not fabricate quiz availability, completion or points. The room handles the documented quiz-ready event and has an opt-in browser notification control.

Docker now runs Alembic before starting the API so a fresh volume is migrated before the session startup catch-up reads it. Native startup still requires `make migrate`. Database work on sockets is shielded from disconnect cancellation to ensure SQLite connections return to the pool.

### Verification

- `make test`: 111 backend tests pass, including invite/scoring-storage/streak-storage regressions and 15 session tests; lint/format and frontend lint/TypeScript pass. Only the existing upstream Starlette/httpx deprecation warning remains.
- `make migration-check`: no schema changes. Native frontend and both Docker images build successfully.
- All 64 Chrome/WebKit browser checks pass at 360, 390, 768 and 1440px. Coverage includes group invite signup/login auto-join, solo socket/pause-through-leave/rejoin/reload, two live learners on different topics through the Next.js WebSocket proxy, and overflow/navigation/PWA checks. Mobile/desktop session screenshots were visually reviewed. Actual Safari/device verification remains for step 9.
- Fresh disposable Docker database: automatic Alembic migrations, startup catch-up, health, signup/login, group/invite creation, solo start and authenticated heartbeat socket pass. The test container is removed; the app preview uses the existing persistent volume.
- A final access regression confirms that a former LIVE host cannot list the room after leaving its group. Active-time tests cover exact 120-second grace, 121-second gaps, fractional carry, multiple sockets, required time, scheduled starts without participants, late joins, Lagos midnight, snapshot preservation, incomplete end and early-finish deadline anchoring.

## Step 6

Applied the confirmed archive behavior and historical shared-goal denominator. No migration is needed: membership intervals and `is_active` already preserve these facts.

FastAPI background tasks enqueue per-participant quiz work after commit. Scheduled rooms enqueue at server-held start; startup recovers persisted pending work. One asyncio worker serialises Ollama calls and coalesces matching subject/topic/level/prompt-version keys. Ollama receives the document prompt and Pydantic JSON schema via `format`, `stream=false`, temperature 0.4, with a 120-second whole-request deadline and one retry containing validation feedback. No model is substituted if the configured model is missing.

Validation enforces question/option sizes, distinct normalised options/questions, strict answer indices, difficulty values and 5/6/4 mix, banned options and a small local content blocklist. Options are shuffled before storage and indices remapped. Safe endpoints return no answer indices/explanations until the owner submits. GET opens/resumes the attempt per the design; POST `/quiz/start` is an explicit idempotent alias. Timers and the effective deadline survive reloads. Duplicate identical submissions return the original result; different resubmissions fail.

Cache hits precede generation; after failure the worker rechecks exact cache, then same-subject/level related cache, excluding attempted, retired, flagged or disabled variants. An entire variant containing a flagged question is excluded from new assignments, preserving 15 questions. Open attempts retain their immutable question/options mapping and earned results; flagging never recalculates a score. Five active variants are retained per key; logical eviction retires old variants to preserve historical attempts. Single inappropriate or three distinct-user flags disable the question and retire the variant. Only submitted owners can flag, once per question; notes stay private.

Unavailable or expired quizzes retain active-time completion and base/live points, subject to the daily cap and membership rules. Step 6 introduces those fallback ledger writes; step 7 adds quiz/improvement points and baseline counting. Insufficient time earns nothing. Camera/focus data is never read by completion or quiz logic.

`make seed-quizzes` stores three validated, curated SS2 fallback topics: Chemistry/Mole concept, Chemistry/Alkenes, Mathematics/Indices. Repeated seeds never resurrect flagged variants. Docker applies migrations and seeds these fallbacks before startup. The full week-history demo seed remains step 10.

Responsive quiz/result screens include 1–4 / Enter shortcuts, local draft recovery, server-based countdown, progress/review tracker, personal result explanations and post-submission reporting. Before submission, **Mark for review** is local only; it does not send a question flag early.

References: [Ollama chat API](https://docs.ollama.com/api/chat), [Ollama structured output](https://docs.ollama.com/capabilities/structured-outputs).

Verification: 144 backend tests pass, including mocked valid/retry/failure/timeout generation, cache/flag/repeat rules, queue deduplication, scheduled snapshot use, pending responses and deadline boundaries. Lint/format, frontend lint/TypeScript, production build and migration check pass. All 72 Chrome/WebKit checks pass at 360, 390, 768 and 1440px, including quiz reload, keyboard submission, personal results, flagging and saved group points. Quiz screenshots were visually reviewed. Ollama is offline locally; model output behavior is covered with mocked Ollama and the browser demo uses seeded fallback data. Actual Safari/device verification remains for step 9.
