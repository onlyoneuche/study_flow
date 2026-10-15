# StudyFlow: 2–3 minute demo

Run this locally after the [setup guide](setup.md). This pitch starts a real live session, then explicitly switches to Ada’s **already-studied solo session** to demonstrate its quiz and saved results. Normal timers are 25/45/60 minutes; there is no shortened-duration flag.

## Prepare before the audience arrives

1. Pull `qwen2.5:7b-instruct` and keep Ollama running if showing new AI generation. The prepared quiz and curated SS2 fallback topics also work when Ollama is unavailable.
2. Stop the backend, run `make migrate && make seed`, then `make dev`. For Docker, use the stop/seed/start sequence in the [setup guide](setup.md). Seed immediately before presenting: Ada’s prepared quiz has a real **20-minute** timer starting at seed time. Keep the printed quiz URL handy. A full rebuild is best completed before this final reset.
3. Open localhost:3000 and sign in as `ada@demo.studyflow.example.com` / `StudyFlow-demo-2026!`. Resetting archives the previous generation, so use a fresh sign-in.
4. Optionally sign in as `tunde@demo.studyflow.example.com` with the same password in another browser/private window for live presence. Tunde studies Physics / Forces and motion. Use demo accounts for this; a real account joining the fixture makes later resets refuse safely to protect shared history.
5. Check Home shows Study Squad, around 340/600 points, 12 streak days, one recent frozen day, and a scheduled live room. Counts follow the current Lagos calendar; use the seed’s printed totals if presenting around a week boundary. Keep the answer cues below beside the presentation.

## Present

| Time | Action | Suggested narration |
| --- | --- | --- |
| 0:00–0:20 | Show Ada’s Home: weekly bar, streak, studied-today members and tonight’s Join card. | “We study different subjects but contribute to one squad. Six members have a 600-point weekly target. Solo study counts too. One missed day used a freeze and preserved this 12-day streak.” |
| 0:20–0:40 | Open **Visit your squad**. Show the six members and invite card; copy the link or open **Share on WhatsApp** to show the prefilled message. | “An invite lasts seven days, with a use limit. Friends return here after signing up. Everyone stays in the same age band.” |
| 0:40–1:00 | Click **Study together**; enter **Alkenes**, subject **Chemistry**, retain 25 minutes and click **Start live session**. Optional: Tunde opens Study and joins on his own topic. | “The shared timer uses server time. Each person picks their own subject and topic. Quizzes prepare locally in the background.” |
| 1:00–1:10 | Show connected presence and timer. Click **Leave session**, then open Ada’s printed prepared quiz URL (or Home’s recent study → **Open quiz**). | “This new live room runs for the full 25 minutes. For the short pitch, I’m switching to Ada’s earlier, already-studied Mole concept session.” |
| 1:10–2:00 | Answer the 15 prepared Mole concept questions. Choose the text from the cues below; use 1–4 and Enter on desktop. Submit the final question. | “Answers are shuffled. The server keeps the correct indices private and enforces both the 20-minute quiz limit and the study-end deadline.” |
| 2:00–2:30 | Show Results: private score, own baseline/history, per-squad points, updated weekly bar and streak card. | “A perfect answer set earns 8 study points, 10 quiz points and 7 improvement points: 25 total. Improvement is against Ada’s own Chemistry history. The bar rises from 340 to 365; streaks are checked nightly at 02:00 Lagos, so this stays at 12 for now.” |
| 2:30–2:50 | Open **Ranks**, show Study Squad versus Unilag Brainiacs and Ada’s in-squad position. | “Squads rank by points per member. Inside a squad we compare improvement points, never raw scores across subjects. Past weeks stay in the immutable ledger.” |

The WhatsApp button opens a composer; it does not send automatically. For the pitch, showing the populated message is sufficient. The scheduled Join card represents an actual room, without RSVP counts or fake online members.

Results depend on the answers selected. With 15 correct and the fresh fixture, Ada’s two prior Chemistry scores average 63.3%, producing +7 improvement points. That completion also updates the in-squad improvement ranking. With the standard current-week seed, the bar becomes **365/600**. For other starting totals, add 25 when the prepared session started in the current Lagos week. During the first 26 minutes of Monday, its start belongs to Sunday and its points credit the previous week instead; show that ledger week, or present after this boundary for the standard current-bar story.

## Presenter answer cues

These cues apply only to the seeded **Mole concept** quiz. Options are shuffled, so choose the answer text rather than memorising a letter/number. Questions retain their listed order. These are fixture notes, not answers returned by the pre-submission API.

| Question | Choose |
| --- | --- |
| 1. Particles in one mole | 6.02 × 10²³ particles |
| 2. Unit for amount of substance | mol |
| 3. Molar mass of water | 18 g/mol |
| 4. Moles from mass | Mass ÷ molar mass |
| 5. Molar mass of CO₂ | 44 g/mol |
| 6. Moles in 36 g water | 2 mol |
| 7. Mass of 0.5 mol NaCl | 29.25 g |
| 8. Molecules in 2 mol oxygen | 1.204 × 10²⁴ |
| 9. Gas volume for 0.25 mol | **6 dm³** (not 96 dm³) |
| 10. Concentration of 0.5 mol in 2 dm³ | 0.25 mol/dm³ |
| 11. Hydrogen for 1 mol nitrogen | 3 mol |
| 12. Limiting reactant | Oxygen |
| 13. Empirical formula | CH₂ |
| 14. Oxygen atoms in 0.5 mol CO₂ | 6.02 × 10²³ |
| 15. Volume of solution | 250 cm³ |

## Full session walkthrough and recovery

To show one new session all the way through, allow the actual 25-minute duration, keep the room connected, and then take its quiz. Active study must meet the documented 80% threshold. Live members join within ten minutes for live eligibility; a hidden tab continues presence heartbeats. If suitable cached quizzes have already been used, new generation needs Ollama. The short script above does not pretend the prepared solo quiz belongs to the new live room.

If the prepared quiz expires, late answers cannot be accepted. Ada’s study time still counts as time-only completion with base points. Stop the backend and rerun the seed to refresh the pitch, then restart and sign in again; do not edit timestamps or ledger rows. If seed refuses mixed non-demo data, keep that history and use a separate demo database. Never delete the shared database/volume to reset the fixture.

Optional Focus Tracker segment: enable `FOCUS_TRACKER_ENABLED=true` and restart/recreate the backend before the pitch. The checkbox on Start is still off until selected. Show its local-camera privacy copy and 10-second calibration, then stop it. For an immediate comparison, open the separate **Synthetic focus comparison** URL printed by the refreshed seed: Ada sees 90%, above the anonymous session median of 80% from three valid summaries. State that these are fictional demo measurements from an already-ended live session. New live comparisons wait until 30 minutes after session end. See [tracker details and switch-off instructions](focus-tracker.md). Account anonymisation, optional weekly snapshots, nudges and the full-squad live bonus remain backlog.
