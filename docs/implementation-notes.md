# Implementation notes and open questions

The source of truth is [studyflow-design.md](studyflow-design.md). The user's numbered build order takes precedence over the suggested order in section 10. Supplied HTML references are preserved under `mockups/`; no reference PNGs were supplied.

## Scope decisions from the source

- Group full-live bonus `G` is v2 (§1.2 and §10), so the MVP will not award it.
- Session heartbeats continue while a tab is hidden (§3.3). Only Focus Tracker sampling pauses on a hidden tab (§9.3, §9.5). Hidden-tab pauses must never be labelled away. TODO: ensure the later session UI distinguishes tracker pause from server presence.
- Focus Tracker implementation follows steps 1–11; its table belongs in step 2 as requested. Scoring and streak code must never read it.
- Missing Ollama is a degraded dependency, not an API outage (§3.7). `/health` and `/api/v1/health` return HTTP 200 with detailed dependency state; this avoids blocking startup or Docker liveness when cached quizzes can serve the app. This is an infrastructure choice, not a scoring rule.

## TODO: resolve before implementing the affected rules

- `OTHER` has a level descriptor but no audience-band mapping (§4, §8). Do not infer a band or allow cross-band membership.
- The document's paused-streak pseudocode skips `last_evaluated_date` while startup catch-up uses that field (§2). Preserve idempotent day records and define a catch-up cursor that cannot repeatedly revisit paused days; no streak rule should change.
- Startup before 02:00 Lagos must not finalise yesterday before the last session's quiz window closes (§2). TODO: anchor catch-up to the latest due 02:00 evaluation.
- Quiz timer is 20 minutes (§3.10), submission window is 30 minutes after participant end (§1.1). TODO: enforce both deadlines when quiz endpoints are added.
- `sessions` is described as having a copied level (§4), but live participants can have different levels and the table in §5 has no level column. TODO: retain the per-participant level snapshot and resolve whether a redundant session-level value is intended.
- The mockup's daily goal of two sessions, scheduled-session RSVPs (“going”), member nudges and cross-person quiz-score badges have no corresponding MVP API/rule. TODO: omit unsupported mechanics and show only documented data; never rank raw scores.

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

The installed Next.js lint configuration pulls in `braces` via `fast-glob`/`micromatch`. The registry audit reports five transitive/development advisories rooted in the same `braces` stack-exhaustion issue; the latest published `braces` remains 3.0.3 with no patched version available. These tools process repository files at lint time. The production-only npm audit reports zero advisories. TODO: update the lint dependency chain when a compatible patch is published; do not force a framework downgrade.

Technical references: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation), [Next.js PWA guide](https://nextjs.org/docs/app/guides/progressive-web-apps), [Ollama model-list API](https://docs.ollama.com/api/tags).
