"""Local server for the WP-10 throughput case (never imported by the app).

    BENCH_NO_READ_LOCK=1 python scripts/bench_server.py --port 8231

Runs the real FastAPI app. With BENCH_NO_READ_LOCK set, the Discover route's shared job
read lock is replaced by a no-op at startup (a monkeypatch of the name the route module
calls); nothing under backend/app/ is edited. Local disposable benchmarking only.
"""

import argparse
import sys
from contextlib import nullcontext
from os import environ
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import discover  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8231)
    args = parser.parse_args()
    if environ.get("BENCH_NO_READ_LOCK") == "1":
        discover.job_read_lock = nullcontext  # hold_job_read_lock calls job_read_lock()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
