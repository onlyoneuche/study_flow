"""Create a local configuration once, without overwriting existing secrets."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = root / ".env"
if destination.exists():
    print("Keeping existing .env")
else:
    contents = (
        (root / ".env.example")
        .read_text()
        .replace(
            "replace-with-a-random-secret-of-at-least-32-characters",
            secrets.token_urlsafe(48),
        )
    )
    with destination.open("x") as file:
        file.write(contents)
    destination.chmod(0o600)
    print("Created .env with a random local auth secret")
