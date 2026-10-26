"""Local server for the WP-10 throughput case (never imported by the app).

    BENCH_NO_READ_LOCK=1 python scripts/bench_server.py --port <free port>

Runs the real FastAPI app. With BENCH_NO_READ_LOCK set, the Discover route's shared job
read lock is replaced by a no-op at startup (a monkeypatch of the name the route module
calls); nothing under backend/app/ is edited. Local disposable benchmarking only.
"""

import argparse
import json
import sys
from contextlib import nullcontext
from os import environ
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402
from seed_synthetic import assert_local_urls, assert_no_routing_env, redact_secrets  # noqa: E402

from app.errors import ApiError  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import discover  # noqa: E402


def exception_chain(exc: BaseException) -> list[str]:
    """'Type pgcode=XXXXX: message' per exception in the cause chain.

    Only the exception type, SQLSTATE and the first message line are kept, with URL
    credentials and password=... values redacted and the length capped.
    """
    chain, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        first_line = (str(exc).strip().splitlines() or [""])[0]
        code = getattr(exc, "pgcode", None)
        chain.append(
            f"{type(exc).__name__}{f' pgcode={code}' if code else ''}: {redact_secrets(first_line)}"
        )
        exc = exc.__cause__ or exc.__context__
    return chain


def log_server_errors(path: str) -> None:
    """Append one JSON line per 5xx ApiError with its cause chain (exception types, SQLSTATE
    codes and a redacted, length-capped first message line; see exception_chain)."""
    original = app.exception_handlers[ApiError]

    async def handler(request, exc):
        if exc.status_code >= 500:
            with open(path, "a") as log:
                log.write(json.dumps({"status": exc.status_code, "chain": exception_chain(exc)}))
                log.write("\n")
        return await original(request, exc)

    app.add_exception_handler(ApiError, handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8231)
    args = parser.parse_args()
    assert_no_routing_env()
    assert_local_urls(environ.get("DATABASE_URL", ""), environ.get("MONGODB_URI", ""))
    no_lock = environ.get("BENCH_NO_READ_LOCK") == "1"
    if no_lock:
        discover.job_read_lock = nullcontext  # hold_job_read_lock calls job_read_lock()
    identity = {"token": environ.get("BENCH_TOKEN", ""), "no_read_lock": no_lock}
    # Lets the benchmark prove it talks to the server it just started, in the mode it asked for.
    app.add_api_route("/__bench/identity", lambda: identity, include_in_schema=False)
    if environ.get("BENCH_ERROR_LOG"):
        log_server_errors(environ["BENCH_ERROR_LOG"])
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
