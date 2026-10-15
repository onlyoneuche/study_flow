#!/bin/sh
set -eu
alembic upgrade head
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
python -m app.quizzes.seed
exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
