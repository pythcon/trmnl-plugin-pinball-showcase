"""Regenerate plugin/tests/fixtures from the current OPDB export.

Run from api/: ``uv run python scripts/refresh_fixtures.py``. Uses (and fills) ./data.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from pinball_showcase.config import Settings
from pinball_showcase.main import create_app

OUT = Path(__file__).resolve().parents[2] / "plugin" / "tests" / "fixtures"
FIXTURES = {
    # Modern Stern title: editions, six credit roles, playfield + backglass.
    "modern": "/api/v1/machines/GK17D?tz=America/New_York&date=2026-10-05",
    # 90s DMD classic.
    "classic": "/api/v1/machines/G5pe4?tz=America/New_York&date=2026-10-05",
    # Electro-mechanical era.
    "em": "/api/v1/showcase?era=em&date=2026-10-05",
    # Nearly square backglass (caught a grid blow-out on TRMNL X).
    "square_art": "/api/v1/machines/GrleW-MYeod?tz=America/New_York&date=2026-10-05",
    # Very long title.
    "long_name": "/api/v1/showcase?keyword=wonka&date=2026-10-05",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=Path("data"), public_url="https://pinball-showcase.trmnlplugins.com")
    with TestClient(create_app(settings)) as client:
        for name, url in FIXTURES.items():
            payload = client.get(url).json()
            (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")
            print(f"{name}: {payload['machine']['name']}")
    no_matches = {
        "error": {
            "title": "No matches",
            "message": "No machines match these filters. Try widening them.",
        }
    }
    (OUT / "no_matches.json").write_text(json.dumps(no_matches, indent=2) + "\n")


if __name__ == "__main__":
    main()
