# Minimal Focus Tracker

This implements §9.13 only, with the user's requested **10-second calibration** replacing its five seconds. It is a self-reflection estimate from face presence and head pose, with no blink, eyes-closed or gaze signal. It cannot measure learning or attention directly and has no effect on points, streaks, goals or rankings.

## Enable or switch off

Set `FOCUS_TRACKER_ENABLED=true` in the root `.env`, then restart the native backend. In Docker, recreate the backend so Compose reloads `.env`:

```sh
docker compose up -d --force-recreate backend
```

Set the flag to `false` and repeat to switch it off. No frontend rebuild is required. Open pages check the flag every 15 seconds; after the backend changes, a disabled flag stops active trackers on the next successful check. The checked-in example defaults to false. The current local demo can enable the feature while every individual session's checkbox remains **off by default**.

On **Study → New session**, opt in before starting. Friends can also opt in on the live join form. There is no saved preference across sessions. Camera permission is requested only after opting in and joining/starting an active participation. A future scheduled room waits until its actual start. A denied permission or unsupported device leaves study working normally.

Calibration takes ten visible one-second checks: look at the screen for the first five seconds, then at your notes for five. The median screen pose becomes neutral; at least eight of ten checks must see a face. After calibration, yaw within ±30° and pitch from −45° down to +20° up count as head-aligned. Looking at notes is allowed. A face-present look-away of at most five checks is forgiven. A face-absent run of at most 20 checks is forgiven; longer absent runs count entirely as time away. Pauses split these runs.

Checks run at a fixed 1 fps in a classic Web Worker. Hidden tabs pause checks and accrue paused seconds; they never count as away. Presence heartbeats continue independently. **Stop Focus Tracker**, Leave, session end, navigation away and sign-out stop camera tracks. A detection taking over 500 ms disables the tracker and retains a partial numeric summary; load failures and a hung-worker watchdog stop it too. Minimal mode has no adaptive rates, battery hints or retention job.

## Privacy and delivery

Video is requested at 320×240 with audio off. Frames transfer only to the local worker as ImageBitmaps; each bitmap is closed after use. Landmarks and poses are discarded in the worker after classification. No recording or canvas/image export API is used. The worker returns status and aggregate counters, never landmarks or images. No focus data travels over WebSockets.

Only `{opted_in, attentive_pct, away_seconds, samples, paused_seconds, sample_fps, tracker_version}` is posted to the API, once per participation after study ends. The server rejects extra fields, non-numeric metrics and out-of-bounds values. Percentages use half-up rounding over sampled, non-paused checks. Summaries are self-reported and are not evidence of behaviour.

Stopping early keeps an aggregate draft in this tab's session storage; remaining stopped time counts as paused. While the app stays open and the learner is signed in, a small retry queue submits at session end. It also handles network failures until the 30-minute deadline. Closing the browser before the worker can return its final aggregate can lose that partial data; there is no background camera or service-worker upload. Study/points remain unaffected. Calibration frames do not enter the score or coverage count.

A valid summary needs at least 60 samples and at least 50% coverage of server-counted active participation time. Insufficient data stays visible as a personal estimate marked **Not enough camera data**, and is excluded from comparison. Metrics are owner-only. The comparison requires an ended session and a **closed end + 30-minute window**, so submission order cannot change a published comparison. It includes only valid opted-in summaries from that session, including the viewer. Fewer than three yields personal only; solo always yields personal only. The response gives only the viewer's metrics, count, median and above/around/below position (±5 is around), with no identities or individual peer scores.

Routes behind the flag:

- `POST /api/v1/participants/{id}/focus-summary` — owner only, one submission; rejects late/repeated writes.
- `GET /api/v1/participants/{id}/focus-summary` — own summary immediately, including while comparison is pending.
- `GET /api/v1/sessions/{id}/focus-comparison` — participant only; 409 until the comparison window closes.
- `GET /api/v1/features` — public boolean flag only; disabled focus routes return 404.

The summary table already existed; no migration or scoring change is needed. SQL-guard regression tests reject any focus-table access while completion, streak evaluation and leaderboards run. Existing score-independence tests also compare 0% and 100% summaries.

## Demo and checks

`make seed` adds three **synthetic** valid focus summaries (90%, 80%, 70%) to an already-ended live history session, prints its results URL, and preserves the 340/600 weekly target fixture. Log in as Ada and open that printed URL: her card shows 90%, above the anonymous 80% median from three valid summaries. These numbers are fictional fixture data, not camera measurements. Tonight's scheduled room has no future camera data; its comparison must wait for normal study and the post-session window.

```sh
make test
make test-focus
```

`make test-focus` builds the frontend and starts a disposable seeded database with the flag enabled. Chrome 390px and WebKit 1440px cover the mocked-worker calibration/pause/stop/numeric submission flow, partial result, anonymous seeded comparison, disabled flag, runtime kill switch and slow-worker failure. A second check runs the actual MediaPipe worker/WASM/model on blank synthetic frames in both engines; it never opens a physical camera. Physical camera accuracy, lighting, pose and low-end-device performance still need manual testing. Existing responsive checks cover Chrome/WebKit at 360/390/768/1440px.

## Self-hosted assets and attribution

The dependency is pinned to `@mediapipe/tasks-vision` **1.1.1**. `frontend/scripts/focus-assets.mjs` copies its matching WASM variants into `public/focus-assets/` before dev/build, and downloads the official versioned `float16/1/face_landmarker.task` model if absent. The model SHA-256 is pinned to `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`. Generated assets are ignored by Git and included in the production/Docker public directory; setup/build needs internet for the first model download. Browser loading uses the app's own origin, only after opt-in. No CDN, hosted inference or paid API is used at runtime.

The implementation follows Google's [Face Landmarker web guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/web_js), which recommends workers for synchronous inference. The [model overview](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) links the component model cards. The [BlazeFace card](https://storage.googleapis.com/mediapipe-assets/MediaPipe%20BlazeFace%20Model%20Card%20%28Short%20Range%29.pdf), [Face Mesh V2 card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf) and [Blendshape V2 card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf) describe the models and their limitations/licensing. Blendshape output is disabled in this minimal implementation. Apache licence and attribution files are under `frontend/vendor/mediapipe/`, copied alongside the generated public assets.

Pose extraction uses the forward axis of MediaPipe’s column-major canonical-to-camera matrix, with metric Y pointing up. Negative pitch therefore means looking down; directional matrix tests cover the wider notes allowance. References: [matrix storage](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/framework/formats/matrix_data.proto) and [screen-to-metric conversion](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/cc/vision/face_geometry/libs/geometry_pipeline.cc).
