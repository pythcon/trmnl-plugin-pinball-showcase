"""Shared fixtures: a tiny synthetic OPDB export that exercises every code path."""

from __future__ import annotations

from typing import Any

import pytest

from pinball_showcase.config import Settings
from pinball_showcase.dataset import Dataset, build_dataset


def image(kind: str, uid: str, w: int = 1224, h: int = 831) -> dict[str, Any]:
    return {
        "group": uid,
        "primary": True,
        "type": kind,
        "urls": {s: f"https://img.opdb.org/{uid}-{s}.jpg" for s in ("small", "medium", "large")},
        "sizes": {"large": {"width": w, "height": h}, "medium": {"width": 640, "height": 435}},
    }


def machine(
    opdb_id: str,
    name: str,
    *,
    year: int,
    date: str | None = None,
    maker: str = "Williams",
    type_: str = "ss",
    display: str = "dmd",
    images: list[dict[str, Any]] | None = None,
    features: list[tuple[str, str]] | None = None,
    people: list[tuple[str, str]] | None = None,
    physical: bool = True,
    short_name: str | None = None,
) -> dict[str, Any]:
    return {
        "opdbId": opdb_id,
        "opdbGroup": opdb_id.split("-")[0],
        "entryType": "machine",
        "name": name,
        "shortName": short_name,
        "year": year,
        "manufactureDate": date or f"{year}-01-01",
        "type": type_,
        "display": display,
        "playerCount": 4,
        "physicalMachine": physical,
        "manufacturer": {"manufacturerId": 1, "name": maker, "fullName": f"{maker} Inc."},
        "ipdbId": 1,
        "people": [
            {"opdbPersonId": i, "name": n, "role": r, "index": i}
            for i, (n, r) in enumerate(people or [])
        ],
        "images": images if images is not None else [image("backglass", f"{opdb_id}-bg")],
        "features": [{"featureId": 0, "name": n, "group": g} for n, g in features or []],
        "keywords": [],
    }


def group(opdb_id: str, name: str, short_name: str | None = None) -> dict[str, Any]:
    return {"opdbId": opdb_id, "entryType": "machineGroup", "name": name, "shortName": short_name}


def sample_export() -> dict[str, Any]:
    return {
        "entries": [
            group("GAAAA", "Medieval Madness", "MM"),
            machine(
                "GAAAA-M0001",
                "Medieval Madness",
                year=1997,
                date="1997-06-25",
                short_name="MM",
                people=[
                    ("Brian Eddy", "design"),
                    ("John Youssi", "art"),
                    ("Dan Forden", "music"),
                    ("Dan Forden", "sound"),
                ],
                images=[image("backglass", "mm-bg"), image("playfield", "mm-pf", 897, 1500)],
            ),
            machine(
                "GAAAA-M0002",
                "Medieval Madness (Remake LE)",
                year=2015,
                maker="Chicago Gaming",
                features=[("Limited edition", "edition"), ("Remake", "edition")],
            ),
            group("GBBBB", "Godzilla"),
            machine(
                "GBBBB-M0001",
                "Godzilla (Premium/LE)",
                year=2021,
                maker="Stern",
                display="lcd",
                images=[],
                features=[("Premium edition", "edition"), ("Limited edition", "edition")],
            ),
            machine(
                "GBBBB-M0002",
                "Godzilla (Pro)",
                year=2021,
                maker="Stern",
                display="lcd",
                features=[("Pro edition", "edition")],
            ),
            group("GCCCC", "Gold Star"),
            machine(
                "GCCCC-M0001", "Gold Star", year=1954, maker="Gottlieb", type_="em", display="reels"
            ),
            group("GDDDD", "Attack from Mars"),
            machine("GDDDD-M0001", "Attack from Mars", year=1995, maker="Bally"),
            group("GEEEE", "Virtual Only"),
            machine("GEEEE-M0001", "Virtual Only", year=2000, physical=False),
            group("GFFFF", "No Images"),
            machine("GFFFF-M0001", "No Images", year=1980, display="alphanumeric", images=[]),
            {"opdbId": "GDDDD-M0001-A0001", "entryType": "alias", "name": "AFM (alias)"},
        ]
    }


@pytest.fixture
def export() -> dict[str, Any]:
    return sample_export()


@pytest.fixture
def dataset(export: dict[str, Any]) -> Dataset:
    return build_dataset(export)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        opdb_export_url="https://example.test/opdb-v2.json",
        min_entries=1,
        retry_minutes=1,
    )
