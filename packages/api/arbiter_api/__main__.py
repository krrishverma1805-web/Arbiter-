from __future__ import annotations

import os
import sys


def _serve() -> None:
    import uvicorn

    uvicorn.run(
        "arbiter_api.app:app",
        host=os.environ.get("ARBITER_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("ARBITER_API_PORT", "8000")),
        reload=os.environ.get("ARBITER_ENV", "dev") == "dev",
    )


def _issue_key(args: list[str]) -> None:
    """arbiter-api issue-key --org <id> --subject <name> [--role viewer|analyst|admin]"""
    from arbiter_api.auth import issue_key

    opts: dict[str, str] = {}
    it = iter(args)
    for a in it:
        if a.startswith("--"):
            opts[a[2:]] = next(it, "")
    org = opts.get("org")
    subject = opts.get("subject", "api-client")
    role = opts.get("role", "analyst")
    if not org:
        sys.exit("usage: arbiter-api issue-key --org <id> --subject <name> [--role <role>]")
    print(issue_key(org, subject, role))


def _worker() -> None:
    from arbiter_api.jobs import worker_loop

    print("arbiter worker: polling for queued jobs (Ctrl-C to stop)")
    worker_loop()


def _db(args: list[str]) -> None:
    """arbiter-api db upgrade|current"""
    from arbiter_api.migrations import current, upgrade

    sub = args[0] if args else "upgrade"
    if sub == "current":
        current()
    else:
        upgrade()
        print("database at head")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "issue-key":
        _issue_key(sys.argv[2:])
    elif cmd == "worker":
        _worker()
    elif cmd == "db":
        _db(sys.argv[2:])
    else:
        _serve()


if __name__ == "__main__":
    main()
