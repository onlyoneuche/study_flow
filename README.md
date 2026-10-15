# StudyFlow

Study together on your own subjects, take AI quizzes, and grow your squad’s points and streak. A local-first hackathon MVP built with Next.js, FastAPI, SQLite and Ollama. No paid APIs or hosted backend.

## Quick start

Requires uv, Node.js 22+, npm, Ollama and make. Keep Ollama running.

```sh
ollama pull qwen2.5:7b-instruct
make setup
make migrate
make seed
make dev
```

Open [localhost:3000](http://localhost:3000). Demo login: `ada@demo.studyflow.example.com` / `StudyFlow-demo-2026!`.

Squads are stored as groups internally.

## Docs

- [Setup, configuration and Docker](docs/setup.md)
- [2–3 minute demo](docs/demo.md) · [Demo data and resets](docs/demo-data.md)
- [Using StudyFlow](docs/usage.md) · [Testing](docs/testing.md)
- [Design and rules](docs/studyflow-design.md) · [Focus Tracker](docs/focus-tracker.md)
- [Limitations and backlog](docs/backlog.md)
- [Working on the project](AGENTS.md)
