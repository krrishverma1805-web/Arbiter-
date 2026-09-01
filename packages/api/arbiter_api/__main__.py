from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    uvicorn.run(
        "arbiter_api.app:app",
        host=os.environ.get("ARBITER_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("ARBITER_API_PORT", "8000")),
        reload=os.environ.get("ARBITER_ENV", "dev") == "dev",
    )


if __name__ == "__main__":
    main()
