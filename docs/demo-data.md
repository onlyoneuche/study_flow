# Demo data and safe resets

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

Friends use their lowercase names at `demo.studyflow.example.com` and the same password. These are fictional verified **SS2 / secondary-band** accounts with fixture consent. The competing **Unilag Brainiacs** has Ife, Musa and Bisi in the same band.

The seed replays heartbeat, session transition, quiz grading, ledger and streak services. Thirteen evaluated days produce a **12-day streak and one freeze used**, with seven recent days of live/solo history and quiz attempts. Today’s extra study brings the weekly bar near **340/600**: six members × the documented 100-point target. The rival has a competing points-per-member average, and a live session is scheduled tonight (19:00 Lagos, or shortly after seed if later).

Actual points and remaining freezes follow the current Lagos calendar. Sunday history can already exceed 340; very early Monday may not have enough elapsed study time to reach it. A freeze in a previous week does not consume this week’s allowance. The seed always prints actual values.

Ada’s prepared quiz belongs to an **already-studied 25-minute solo session**. Its real 20-minute quiz timer starts at seed time: refresh the seed immediately before presenting. New sessions retain their normal **25/45/60-minute** timers. The [short demo](demo.md) explicitly switches from a newly started live room to this prepared participation.

Reset creates a fresh active demo generation and archives the old accounts/squads, disables their invites and cancels their open rooms. Immutable points and study history remain. An ownership registry prevents claiming other accounts by name/email. Non-demo users, squads, existing quiz variants and flags are preserved. Mixed demo/non-demo membership or session history, transferred ownership, or a reserved email collision makes the entire reset refuse safely. For a repeatable pitch, share/copy the invite without joining a real account to the fixture; use another demo member for live presence. Archived generations intentionally remain in the database.
