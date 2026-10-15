# Known limitations and backlog

- Run **one backend instance/worker per database**: WebSocket connections live in memory. An OS lock beside SQLite (`.jobs.lock`) prevents duplicate scheduler owners and seed/server overlap; never remove it while the server runs.
- Local generation can take up to 120 seconds per try and depends on hardware/model availability. Health returns HTTP 200 with `ok` or `degraded` and Ollama details; it is a liveness/dependency check, not a generation-quality or database-readiness check. Cached demo topics work with Ollama unavailable. `make seed-quizzes` adds SS2 Chemistry/Mole concept, Chemistry/Alkenes and Mathematics/Indices without the squad fixture. Reseeding does not revive flagged variants.
- Email delivery is console-only. Guardian consent is a recorded checkbox; guardian email workflows are v2. This is a local hackathon setup with public fictional demo credentials.
- Browser JWTs use session storage. Sign-out clears the browser token, while an issued token remains valid until expiry; logout/password reset do not revoke it server-side. Reset demo generations are inactive and cannot authenticate.
- **Account anonymisation:** resolve the conflict between tombstoning user IDs and append-only ledger history before exposing account deletion.
- **Focus Tracker:** the approved minimal version uses local face presence/head pose at 1 fps, 10-second calibration, pause/forgiveness rules and anonymous post-session comparison. It is disabled globally by default and opt-in per session when enabled. Physical-camera accuracy/performance needs manual checking; retention jobs, blink/gaze and adaptive rates remain deferred. [Details and switch-off instructions](focus-tracker.md).
- **Weekly snapshots:** backlog only. MVP historical weeks are derived from the ledger using Lagos boundaries.
- **Nudges and RSVPs:** omitted for MVP; nudges are v2.
- **Full-squad live bonus G:** v2; no MVP awards.

Steps 1–11 and the approved minimal Focus Tracker are complete. Further tracker features remain out of scope.
