"""Query parameters for the showcase endpoint.

TRMNL renders custom-field values into the polling URL, so the parser is forgiving:
blank values mean "not set", multi-value fields accept repeated parameters and/or
comma-separated lists, and unknown values are ignored rather than rejected.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field

from .selection import (
    DISPLAYS,
    ERA_ALIASES,
    FEATURES,
    MULTI_EDITION,
    ROTATION_ALIASES,
    Era,
    Filters,
    Rotation,
)

Multi = list[str]


class ShowcaseParams(BaseModel):
    model_config = {"extra": "ignore"}

    rotation: str | None = Field(
        None, description="daily | 1h | 2h | 3h | 6h | 12h | refresh | shuffle"
    )
    interval: str | None = Field(
        None, max_length=5, description="Minutes per period for rotation=refresh"
    )
    avoid: Multi = Field(default_factory=list, description="OPDB ids not to repeat (shuffle)")
    tz: str | None = Field(None, max_length=64, description="IANA timezone, e.g. America/New_York")
    date: str | None = Field(None, description="Override the date (YYYY-MM-DD) for previews")
    machine: str | None = Field(None, max_length=40, description="Pin one OPDB id (no rotation)")

    era: Multi = Field(default_factory=list, description="em, early_ss, dmd, modern (ss = all SS)")
    decade: Multi = Field(default_factory=list, description="e.g. 1970, 1990s")
    min_year: str | None = Field(None, max_length=4)
    max_year: str | None = Field(None, max_length=4)
    manufacturer: Multi = Field(default_factory=list, description="Names to include")
    exclude_manufacturer: Multi = Field(default_factory=list, description="Names to exclude")
    display: Multi = Field(default_factory=list, description=", ".join(sorted(DISPLAYS)))
    players: Multi = Field(default_factory=list, description="Player counts, e.g. 1,2,4")
    feature: Multi = Field(default_factory=list, description=", ".join([*FEATURES, MULTI_EDITION]))
    exclude_feature: Multi = Field(default_factory=list)
    keyword: Multi = Field(default_factory=list, description="Words in the title (themes)")
    exclude_keyword: Multi = Field(default_factory=list)
    person: Multi = Field(default_factory=list, description="Designers, artists, coders...")
    favorites: Multi = Field(default_factory=list, description="OPDB ids to rotate through")
    exclude_id: Multi = Field(default_factory=list, description="OPDB ids never to show")
    require_playfield: str | None = Field(None, description="true to require a playfield image")


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def split_values(values: Iterable[str], limit: int = 50) -> list[str]:
    """Flatten repeated and comma/newline separated values; lowercase, de-duplicate."""
    out: list[str] = []
    for value in values:
        for part in value.replace("\n", ",").split(","):
            part = part.strip().lower()
            if part and part not in out:
                out.append(part[:80])
    return out[:limit]


def parse_year(value: str | None) -> int | None:
    value = blank_to_none(value)
    if value and value.isdigit() and 1800 <= int(value) <= 2200:
        return int(value)
    return None


def parse_bool(value: str | None) -> bool:
    return (blank_to_none(value) or "").lower() in {"1", "true", "yes", "on"}


def parse_rotation(value: str | None) -> Rotation:
    key = (blank_to_none(value) or "daily").lower()
    if key in ROTATION_ALIASES:
        return ROTATION_ALIASES[key]
    try:
        return Rotation(key)
    except ValueError:
        return Rotation.DAILY


def parse_interval(value: str | None) -> int | None:
    value = blank_to_none(value)
    return int(value) if value and value.isdigit() else None


def _eras(values: Iterable[str]) -> frozenset[Era]:
    eras: set[Era] = set()
    for value in split_values(values):
        if value in ERA_ALIASES:
            eras |= ERA_ALIASES[value]
            continue
        try:
            eras.add(Era(value))
        except ValueError:
            continue
    return frozenset(eras)


def _decades(values: Iterable[str]) -> frozenset[int]:
    decades: set[int] = set()
    for value in split_values(values):
        digits = value.rstrip("s").lstrip("'")
        if digits.isdigit():
            year = int(digits)
            if year < 100:  # "70s" -> 1970
                year += 1900 if year >= 30 else 2000
            if 1800 <= year <= 2200:
                decades.add(year // 10 * 10)
    return frozenset(decades)


def parse_ids(values: Iterable[str]) -> tuple[str, ...]:
    # OPDB ids are case-sensitive; split without lowercasing.
    out: list[str] = []
    for value in values:
        for part in value.replace("\n", ",").split(","):
            part = part.strip()
            if part and part not in out:
                out.append(part[:40])
    return tuple(out[:200])


def to_filters(p: ShowcaseParams) -> Filters:
    features = set(FEATURES) | {MULTI_EDITION}
    return Filters(
        eras=_eras(p.era),
        decades=_decades(p.decade),
        min_year=parse_year(p.min_year),
        max_year=parse_year(p.max_year),
        manufacturers=tuple(split_values(p.manufacturer)),
        exclude_manufacturers=tuple(split_values(p.exclude_manufacturer)),
        displays=frozenset(v for v in split_values(p.display) if v in DISPLAYS),
        players=frozenset(int(v) for v in split_values(p.players) if v.isdigit()),
        features=frozenset(v for v in split_values(p.feature) if v in features),
        exclude_features=frozenset(v for v in split_values(p.exclude_feature) if v in features),
        keywords=tuple(split_values(p.keyword)),
        exclude_keywords=tuple(split_values(p.exclude_keyword)),
        people=tuple(split_values(p.person)),
        favorites=parse_ids(p.favorites),
        exclude_ids=parse_ids(p.exclude_id),
        require_playfield=parse_bool(p.require_playfield),
    )
