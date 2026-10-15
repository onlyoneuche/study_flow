# Implementation notes and open questions

The source of truth is [studyflow-design.md](studyflow-design.md). The user's numbered build order takes precedence over the suggested order in section 10. Supplied HTML references are preserved under `mockups/`; no reference PNGs were supplied.

## Scope decisions from the source

- Group full-live bonus `G` is v2 (§1.2 and §10), so the MVP will not award it.
- Session heartbeats continue while a tab is hidden (§3.3). Only Focus Tracker sampling pauses on a hidden tab (§9.3, §9.5). Hidden-tab pauses must never be labelled away. The session UI keeps these separate; camera tracking remains off for MVP.
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

## Step 7

Completed `B + Q + I + L` scoring with half-up rounding, welcome improvement points, non-negative capped improvement and the last three counted same-user/subject/participant-level attempts. Each valid submission stores its baseline, seeds the next baseline and completes/awards in one SQLite write transaction. The daily cap affects points only; valid timely quiz attempts still count for the subject baseline. Unavailable/deadline fallbacks have base/live only and never enter it. The v2 full-group bonus remains absent.

One participation writes base/quiz/improvement to all current memberships and live credit only to its host group, with the existing per-participant/group/component uniqueness guard. The first three completions per Lagos session day earn points; additional sessions store a zero daily-cap row in each group and still complete. Retries cannot change baseline or add points twice. The immutable ledger supports corrections through adjustment rows only. Focus summaries are never read by scoring; a regression varies them without changing awards.

Added group weekly points/bar and private member-improvement ranking, same-band group leaderboard by points/member then streak, and own paginated ledger endpoints. Rankings contain no raw quiz scores. Individual ties count distinct credited participations, including daily-cap completions. Improvement-reversing adjustment rows affect the improvement ranking without rewriting history. New Ranks and points-history screens display these documented aggregates, with the full visual dashboard pass still in step 9.

Browser checks now create/migrate/seed a disposable `/tmp/studyflow-…` database automatically and refuse reuse of an existing backend server. Their persisted-time fixture remains test-only, with no application clock-bypass endpoint. Auth expiry in a room/quiz offers sign-in with a return destination; the saved attempt timer remains unchanged.

Migration 0003 corrects the archive/profile edge: historical ownership of an inactive group no longer prevents the former owner from changing audience band. Active memberships/ownership still enforce band separation. A regression verifies that the profile transition leaves archived ledger history intact.

### Verification

- `make test`: 165 backend tests pass, including 21 scoring/points tests and all scoring-storage, streak-storage, invite and mocked-Ollama regressions. Lint/format and frontend lint/TypeScript pass. Only the existing upstream Starlette/httpx test-client warning remains.
- The document example produces 30 LIVE / 25 SOLO points with 41 active minutes, 11/15 correct and a 60% baseline. Tests cover 0/1/2/3+ prior attempts, snapshot/subject isolation, clamping/rounding, three-group credit, host-only live bonus, concurrent daily-cap completion, cap reset by Lagos session day, time-only fallbacks, append-only/idempotent awards, private ledger, same-band averages, tie-breaks, adjustments, archived-owner profile changes and focus independence.
- All 72 Chrome/WebKit browser checks pass at 360, 390, 768 and 1440px, including quiz reload/shortcuts, results/reporting, saved group points, rankings and points history. Native/Docker production builds and schema checks pass; rankings screenshots were visually reviewed. Actual Safari/device verification remains for step 9.
- A fresh disposable Docker database migrated through revision 0003 and seeded fallback quizzes automatically. The real API passed signup/login, cached quiz preparation, server-held attempt, submission, full B/Q/I awards, group bar, improvement ranking, ledger and inappropriate-flag retirement while preserving the submitted result. The disposable container is removed and the app preview is restored using its existing persistent volume.
- Local Ollama is offline, so generated response/retry/timeout cases use a mocked Ollama transport; the real-browser/container demo exercises curated local fallback. No paid or hosted service is used.

## Step 8

Implemented nightly Lagos streak evaluation and chronological startup catch-up. The user's latest decision replaces the original end-of-day eligibility rule: membership is fixed at day-start, including later departures/removals, excluding later joins. The design now reflects that decision. Live, solo, capped and time-only completions share the documented completed status; streaks never read quiz scores, ledger amounts or focus summaries.

Each day's streak, best, freeze, audit counts and cursor commit atomically under SQLite write intent. Paused days advance the cursor. A fresh group's first evaluated date is its creation date, so there are no pre-creation records. Startup settles overdue participations before evaluating days. APScheduler uses explicit Africa/Lagos cron triggers (daily 02:00 and Monday 00:00), coalescing/misfire recovery, and a database-adjacent OS lock that rejects a second runtime owner. Per-job async locking and unique day records protect reruns as well.

Weekly reset is a ledger query boundary, with no destructive updates; group views now use the same injected server clock as points endpoints. Sunday evaluations use Sunday's freeze week even though the job runs Monday. No schema change was needed.

TODO: the design's optional `snapshot_weekly_leaderboard` pseudocode does not specify storage or API. Historical ledger queries work; no snapshot table or ranking rules were invented. Account anonymisation remains in the backlog.

Verification: `make test` passes all 189 backend tests and frontend lint/TypeScript. The 24 new streak tests cover kept/frozen/broken/paused days, zero-streak conservation, day-start membership boundaries, mixed live/solo and duplicate completions, multi-day catch-up, 02:00 restart boundaries, DST-free Lagos dates, Monday allowance/bar switching without ledger loss, archived/new groups, transaction rollback, concurrent catch-up, lock ownership/release and cron scheduling.

## Step 9

Completed the mockup-based responsive screens with real data: authenticated Home/dashboard and empty state; group selection, weekly bar, streak audit, freeze allowance, daily session goal, studied-today members and scheduled/running live rooms; session creation with recent topics; centred room timer and members/weekly bar; quiz and review tracker; three-column desktop results with per-group ledger totals and private score history; side-by-side desktop group/improvement leaderboards. Auth, invites, profile, ledger and PWA flows remain integrated. Removed the unused scaffold placeholder route. RSVP counts, nudges and cross-person raw-score badges remain omitted.

Added a private dashboard aggregation route and owner-only completed-result read route. The latter allows time-only results after a rejected late quiz start without extending either deadline. Group views expose documented completion counts per current member and the last seven recorded streak outcomes. The results chart uses only the learner's same-subject/level counted quizzes through that completion. No schema or scoring changes.

Navigation disables automatic prefetching to reduce background requests on slow connections. Assets/fonts stay local, no camera/model bundle is loaded in the browser, and the service worker still caches only the public offline fallback. Quiz-ready notifications use the service worker when available and show clear feedback when notifications are unsupported/denied. Long names/topics wrap, controls remain large, and breakpoint units are consistent so tablet styles cannot override the desktop three-column layout.

Verification: all 195 backend tests, lint/format, frontend lint/TypeScript, production build, migration agreement and both Docker builds pass. The full 80-check production-browser suite passed, followed by 32 targeted session/dashboard/quiz checks after the final display and result-link refinements, in installed Chrome and Playwright WebKit at 360, 390, 768 and 1440px. Coverage includes account/consent flows, invite redirect/auto-join, solo and multi-person live sockets, timer/reload, quiz keyboard controls, option privacy, submission/flags, results-to-dashboard progress, leaderboard/ledger, responsive layouts and PWA/offline recovery. Screenshots of Home, session, quiz and results were reviewed. The API-failure injection test blocks service workers only in that test file so WebKit routing reaches Playwright; the separate PWA tests keep workers enabled.

Native Safari: the user opened a window after the tool initially reported none. Public Home and sign-up/guardian-consent rendering were visually checked in desktop Safari against the local production preview. Native web-element clicks/window resizing repeatedly failed with `elementHasNoFrame` / `noWindowsAvailable`; the full native Safari width matrix and physical-device pass remain manual. All four sizes are covered by WebKit automation; do not label that as a full native Safari/device pass.

No new game-rule ambiguities. Optional weekly snapshot storage and account anonymisation remain TODOs. Focus Tracker remains stretch work after steps 10–11.

## Step 10

Added `make seed` with nine fictional verified SS2 accounts: Ada, Tunde, Zainab, Chidi, Emeka and Funmi in Study Squad, plus three members in Lagos Brainiacs. Each main member has a distinct subject. History replays real heartbeat, session transition, shared quiz grading, completion/ledger and streak services. Thirteen evaluated days include a missed day with one freeze, producing a 12-day current streak; seven recent days include solo/live study and completed quizzes. Seeded current-week time-only sessions bring the bar near 340 points and give the competitor a higher per-member average. Calendar boundaries remain real: Sunday history can exceed that target, and early Monday may have too little elapsed time to reach it.

The documented weekly target is 100 × current members, so six-member Study Squad shows 340/600, rather than inventing a 500-point target. Tonight's scheduled room appears on Home. Ada has an already-studied 25-minute SOLO session with a ready, opened quiz for the short pitch. Its genuine 20-minute attempt timer starts at seed; the presenter must refresh the fixture shortly before presenting. New live sessions retain the documented 25/45/60-minute durations. The guide explicitly switches between those two sessions.

Migration 0004 adds an explicit demo ownership registry. Reset is atomic and uses the scheduler's single-instance lock: stop the backend first. It archives owned groups/accounts and disables their invites, preserving all immutable ledger and study history. It never infers ownership from an email/name. Reserved-address collisions, mixed non-demo membership/session history or transferred non-demo ownership cause a full rollback. Historical quiz imports use the shared validator/shuffler but do not evict active non-demo cache variants; existing flags remain intact. Old demo tokens become inactive, so sign in again after reset. Retained generations grow intentionally; no ledger purge was added.

Docker now uses the migration wrapper as its ENTRYPOINT, so explicit one-off seed commands migrate first. Default startup still seeds the three curated fallback topics. Seed commands use their own cache-preserving transaction. Corrected the single-freeze label and added a separate seeded-browser walkthrough; its answer selection uses exact text because shuffled distractors can contain the correct answer as a suffix (6 versus 96).

Verification: all 209 backend tests pass, including 14 new seed checks for real points/streak history, rerun ownership safety, rollback, locking, calendar boundaries, cache/flag preservation and HTTP login/quiz/leaderboard integration. Backend lint/format and frontend lint/TypeScript pass. Production build and the seeded walkthrough pass in installed Chrome at 390px and WebKit at 1440px, including invite sharing, a real live socket, the prepared quiz, a perfect result adding 25 points, and rankings. Native migration/schema check and repeated native/Docker seeding pass; both Docker images build. The step 9 responsive matrix remains applicable.

User decision: optional weekly snapshots are backlog; MVP past weeks come from ledger queries using Lagos week boundaries. No new scoring/streak ambiguity remains. Account anonymisation, Focus Tracker, nudges and the v2 full-group bonus remain deferred.
