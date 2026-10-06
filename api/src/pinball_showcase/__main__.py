"""``python -m pinball_showcase`` / ``pinball-showcase``: run the API with uvicorn."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "pinball_showcase.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=os.environ.get("PINBALL_LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
