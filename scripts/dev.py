"""Run both development servers and stop both when either exits or Ctrl-C is pressed."""

import os
import signal
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
processes: list[subprocess.Popen] = []


def stop(_signum=None, _frame=None):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
try:
    processes.append(
        subprocess.Popen(
            [
                "uv",
                "run",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=root / "backend",
            start_new_session=True,
        )
    )
    processes.append(
        subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=root / "frontend",
            start_new_session=True,
        )
    )
    while all(process.poll() is None for process in processes):
        time.sleep(0.25)
    raise SystemExit(
        next(
            process.returncode
            for process in processes
            if process.returncode is not None
        )
    )
except KeyboardInterrupt:
    pass
finally:
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
