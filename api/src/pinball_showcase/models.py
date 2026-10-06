"""Typed view of the OPDB v2 export, keeping only the fields the showcase uses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class Image:
    type: str  # backglass | playfield | cabinet | closeup | other
    primary: bool
    title: str | None
    urls: dict[str, str]  # small | medium | large
    sizes: dict[str, tuple[int, int]]

    def url(self, size: str = "large") -> str | None:
        return self.urls.get(size) or self.urls.get("medium") or self.urls.get("small")


@dataclass(frozen=True, slots=True)
class Person:
    name: str
    role: str
    index: int


@dataclass(frozen=True, slots=True)
class Machine:
    opdb_id: str
    group_id: str
    name: str
    short_name: str | None
    common_name: str | None
    year: int | None
    manufacture_date: date | None
    type: str | None  # em | ss | me
    display: str | None  # reels | alphanumeric | lights | dmd | lcd | cga
    players: int | None
    physical: bool
    manufacturer: str | None
    manufacturer_full: str | None
    ipdb_id: int | None
    primer_url: str | None
    rules_url: str | None
    cards_url: str | None = None
    bobs_guide_url: str | None = None
    competition_setup_url: str | None = None
    competition_notes_url: str | None = None
    description: str | None = None
    features: tuple[tuple[str, str], ...] = ()  # (name, group)
    people: tuple[Person, ...] = ()
    images: tuple[Image, ...] = ()
    keywords: tuple[str, ...] = field(default_factory=tuple)
    # OPDB alias entries are full editions (own photos, features, people) of a machine.
    alias_of: str | None = None

    @property
    def edition_features(self) -> tuple[str, ...]:
        return tuple(name for name, group in self.features if group == "edition")

    def image(self, kind: str) -> Image | None:
        candidates = [img for img in self.images if img.type == kind]
        if not candidates:
            return None
        return next((img for img in candidates if img.primary), candidates[0])

    @property
    def has_backglass(self) -> bool:
        return self.image("backglass") is not None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_image(raw: dict[str, Any]) -> Image | None:
    urls = {k: v for k, v in (raw.get("urls") or {}).items() if isinstance(v, str) and v}
    if not urls:
        return None
    sizes = {
        k: (int(v.get("width") or 0), int(v.get("height") or 0))
        for k, v in (raw.get("sizes") or {}).items()
        if isinstance(v, dict)
    }
    return Image(
        type=str(raw.get("type") or "other"),
        primary=bool(raw.get("primary")),
        title=(raw.get("title") or None),
        urls=urls,
        sizes=sizes,
    )


def parse_machine(raw: dict[str, Any], *, alias_of: str | None = None) -> Machine:
    manufacturer = raw.get("manufacturer") or {}
    people = tuple(
        sorted(
            (
                Person(
                    name=p["name"], role=str(p.get("role") or ""), index=int(p.get("index") or 0)
                )
                for p in raw.get("people") or []
                if p.get("name")
            ),
            key=lambda p: p.index,
        )
    )
    images = tuple(img for img in map(_parse_image, raw.get("images") or []) if img)
    return Machine(
        opdb_id=raw["opdbId"],
        group_id=raw.get("opdbGroup") or raw["opdbId"].split("-")[0],
        name=raw.get("name") or raw["opdbId"],
        short_name=raw.get("shortName") or None,
        common_name=raw.get("commonName") or None,
        year=raw.get("year"),
        manufacture_date=_parse_date(raw.get("manufactureDate")),
        type=raw.get("type"),
        display=raw.get("display"),
        players=raw.get("playerCount"),
        physical=bool(raw.get("physicalMachine")),
        manufacturer=manufacturer.get("name"),
        manufacturer_full=manufacturer.get("fullName"),
        ipdb_id=raw.get("ipdbId"),
        primer_url=raw.get("pinballPrimerUrl"),
        rules_url=raw.get("pinballRulesUrl"),
        cards_url=raw.get("pinballCardsUrl"),
        bobs_guide_url=raw.get("bobsGuideUrl"),
        competition_setup_url=raw.get("competitionSetupUrl"),
        competition_notes_url=raw.get("competitionNotesUrl"),
        description=(raw.get("description") or "").strip() or None,
        features=tuple(
            (f["name"], str(f.get("group") or ""))
            for f in raw.get("features") or []
            if f.get("name")
        ),
        people=people,
        images=images,
        keywords=tuple(k for k in raw.get("keywords") or [] if isinstance(k, str)),
        alias_of=alias_of,
    )
