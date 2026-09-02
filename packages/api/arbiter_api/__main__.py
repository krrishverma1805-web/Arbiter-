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


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "issue-key":
        _issue_key(sys.argv[2:])
        return
    _serve()


if __name__ == "__main__":
    main()
