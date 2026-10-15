# Testing and PWA checks

```sh
make test             # backend lint/format + tests; frontend lint + TypeScript
make build            # production build with standalone assets
make migration-check  # migrated schema versus models
# Stop app servers/containers before browser checks (ports 3000/8000).
(cd frontend && npx playwright install webkit)
make test-browser     # Chrome + WebKit, 360/390/768/1440px
make test-demo        # seeded pitch, Chrome 390px + WebKit 1440px
make test-focus       # optional tracker + synthetic/mocked worker checks
```

Google Chrome must be installed for Chrome tests. Browser runners create disposable `/tmp/studyflow-…` databases and migrate them; the seeded demo checks each start with fresh data. Tests cover scoring’s worked example, daily/multi-squad caps, all invite acceptance edge cases, streak/freezes/catch-up/idempotency, auth, sessions, quiz retries/timeouts and safe seed resets.

Last recorded application verification (15 October 2026): **231 backend tests**, backend/frontend checks, production build, migration agreement, repeated native/Docker seed runs, and the seeded end-to-end walkthrough passed. The full responsive suite passed 80 checks across all four widths in Chrome and WebKit. A native Safari desktop visual smoke check passed; full native Safari/device testing at each width remains manual because native input/window automation was intermittent. These are historical results; report fresh checks separately for each change. See [implementation history](implementation-notes.md) for context.

For PWA installation, run the production frontend with `make build` then `npm --prefix frontend run start` alongside the backend, or use Docker. The service worker caches only a public offline page. Authenticated data is never cached, and study/quiz actions require connectivity. Development mode does not register the worker. Devices require HTTPS for installation outside localhost.
