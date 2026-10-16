# StudyFlow

**Study together. Improve together. Keep showing up.**

<img width="1439" height="898" alt="Screenshot 2026-10-16 at 01 05 40" src="https://github.com/user-attachments/assets/0f252039-20c2-470c-a210-8663f302ec28" />

<img width="1437" height="903" alt="Screenshot 2026-10-16 at 01 22 29" src="https://github.com/user-attachments/assets/cb667fbd-63cd-4cce-9ad8-e21b07939731" />

---
StudyFlow is a research-backed, gamified social study app built for the hackathon theme `Engagement & Staying in the Learning Journey`. It helps students stay motivated and keep learning over time instead of dropping off.

Built local-first with FastAPI, Next.js, SQLite and Ollama. It uses no paid APIs and no hosted backend.
Designed by me and developed with [OpenAI Codex](https://openai.com/codex/) as my coding agent.

## Why StudyFlow

Most learners don't quit because the material is too hard. They quit because it's hard to keep showing up alone. StudyFlow tackles this with three things that research links to [persistence](https://doi.org/10.1007/s11423-010-9177-y): [social accountability](https://doi.org/10.3102/0162373713500523), [regular routines](https://doi.org/10.1073/pnas.1921417117) and [visible personal progress](https://doi.org/10.1007/s10648-019-09498-w).

StudyFlow turns studying into a shared daily habit. Friends hold each other accountable through live sessions and a squad streak, a short quiz after every session shows each learner what they've retained, and points reward getting better rather than being the best, so everyone has a reason to come back tomorrow.

## How it works

1. **Form a squad.** Create a squad of 3–8 friends and invite them with a link you can share on WhatsApp.
2. **Study together, each on your own subject.** Join a timed live session with your squad. If you can't make it, do a solo session later. It still counts, but joining live earns bonus points.
3. **Take a quick quiz.** When the timer ends, answer 15 questions on the topic you just studied. A local AI generates them, so no paid service is involved.
4. **Earn points for improving.** You score points for studying, for your quiz result and, most of all, for beating your own recent average. Nobody is ranked on raw scores, because everyone studies different subjects.
5. **Keep your squad's streak going.** The streak grows on every day your squad studies, and each week you fill a shared points bar together. Two streak freezes a week cover off days.

**Optional: Focus Tracker.** Turn on your camera to see how focused you were, compared with others in the session who also used theirs. It runs entirely in your browser, no video leaves your device, and it never affects your points.

## Quick start

Requires uv, Node.js 22+, npm, Ollama and make. Keep Ollama running.

```sh
ollama pull qwen2.5:7b-instruct
make setup
make migrate
make seed
make dev
```

Prefer Docker? Follow the [Docker setup](docs/setup.md#docker-option) for `.env` configuration and demo seeding, then run `docker compose up --build`.

Open [localhost:3000](http://localhost:3000). Demo login: `ada@demo.studyflow.example.com` / `StudyFlow-demo-2026!`.

## Docs

- [Setup, configuration and Docker](docs/setup.md)
- [2–3 minute demo](docs/demo.md) · [Demo data and resets](docs/demo-data.md)
- [Using StudyFlow](docs/usage.md) · [Testing](docs/testing.md)
- [Design and rules](docs/studyflow-design.md) · [Focus Tracker](docs/focus-tracker.md)
- [Limitations and backlog](docs/backlog.md)
- [Working on the project](AGENTS.md)
