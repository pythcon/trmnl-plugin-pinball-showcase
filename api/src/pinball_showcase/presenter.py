"""Turn a featured title into the flat merge-variable payload the TRMNL templates render.

Everything a template needs is pre-computed here (labels, sentences, joined credits) so
the Liquid stays simple and identical across the four layout sizes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import quote_plus

from .dataset import Dataset, Title
from .models import Image, Machine
from .selection import ERA_LABELS, Filters, Rotation, title_era

TYPE_LABELS = {"em": "Electro-mechanical", "ss": "Solid state", "me": "Mechanical"}
DISPLAY_LABELS = {
    "reels": "Score reels",
    "alphanumeric": "Alphanumeric",
    "lights": "Backbox lights",
    "dmd": "Dot matrix",
    "lcd": "LCD",
    "cga": "CGA monitor",
}
ROLE_LABELS = {
    "design": "Design",
    "concept": "Concept",
    "art": "Art",
    "software": "Code",
    "mechanics": "Mechanics",
    "sound": "Sound",
    "music": "Music",
    "dots_animation": "Animation",
    "animation": "Animation",
}
ROLE_ORDER = [
    "design",
    "concept",
    "art",
    "software",
    "mechanics",
    "dots_animation",
    "animation",
    "music",
    "sound",
]
ROTATION_LABELS = {
    Rotation.DAILY: "Pinball of the Day",
    Rotation.EVERY_1H: "Pinball of the Hour",
}
DEFAULT_LABEL = "Pinball Showcase"
TAG_FEATURES = {"Widebody", "Cocktail table", "Add-a-ball", "Head-to-head play"}
SAME_YEAR_LIMIT = 6


def _image_payload(image: Image | None) -> dict[str, Any] | None:
    if image is None:
        return None
    width, height = image.sizes.get("large", (0, 0))
    return {
        "url": image.url("large"),
        "url_medium": image.url("medium"),
        "width": width,
        "height": height,
        "orientation": "portrait" if height > width else "landscape",
    }


def _release_label(machine: Machine) -> str | None:
    d = machine.manufacture_date
    if d is None:
        return str(machine.year) if machine.year else None
    if d.month == 1 and d.day == 1:  # OPDB stores year-only dates as Jan 1
        return str(d.year)
    if d.day == 1:
        return d.strftime("%B %Y")
    return f"{d:%B} {d.day}, {d.year}"


def _has_exact_date(machine: Machine) -> bool:
    d = machine.manufacture_date
    return d is not None and d.day != 1


def _credits(title: Title, rep: Machine | None = None) -> list[dict[str, str]]:
    # Fall back to a sibling edition when the shown one has no people listed.
    shown = rep or title.representative
    machine = next((m for m in [shown, title.representative, *title.machines] if m.people), None)
    if machine is None:
        return []
    by_role: dict[str, list[str]] = {}
    for person in machine.people:
        names = by_role.setdefault(person.role, [])
        if person.name not in names:
            names.append(person.name)
    ordered = sorted(by_role, key=lambda r: ROLE_ORDER.index(r) if r in ROLE_ORDER else 99)
    # One row per role, every name listed; a person with several roles appears on each.
    return [
        {
            "role": ROLE_LABELS.get(role, role.replace("_", " ").capitalize()),
            "names": ", ".join(by_role[role]),
        }
        for role in ordered
    ]


def updated_label(local_now: datetime) -> str:
    """ "Oct 5, 2026 11:42 PM EDT": zones without an abbreviation show their UTC offset."""
    zone = local_now.tzname() or ""
    if not zone or zone[0] in "+-":
        offset = local_now.utcoffset()
        hours = int(offset.total_seconds() // 3600) if offset else 0
        minutes = int(abs(offset.total_seconds()) % 3600 // 60) if offset else 0
        zone = (
            "UTC"
            if not hours and not minutes
            else f"GMT{hours:+d}" + (f":{minutes:02d}" if minutes else "")
        )
    hour = local_now.hour % 12 or 12
    return f"{local_now:%b} {local_now.day}, {local_now.year} {hour}:{local_now:%M %p} {zone}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _years_ago(year: int | None, today: date) -> str | None:
    if not year:
        return None
    diff = today.year - year
    if diff <= 0:
        return "This year"
    return f"{_plural(diff, 'year')} ago"


def opdb_url(machine: Machine) -> str:
    return f"https://opdb.org/search?q={quote_plus(machine.opdb_id)}"


def machine_page_url(site_url: str, machine: Machine) -> str:
    return f"{site_url.rstrip('/')}/m/{quote_plus(machine.opdb_id)}"


def build_showcase(
    dataset: Dataset,
    title: Title,
    *,
    local_now: datetime,
    rotation: Rotation,
    filters: Filters,
    pool_size: int,
    period: str,
    site_url: str,
    edition: Machine | None = None,
) -> dict[str, Any]:
    # A pinned edition id shows that exact edition; otherwise the title's best one.
    rep = edition or title.representative
    page_url = machine_page_url(site_url, rep)
    today = local_now.date()
    era = title_era(title)

    # Edition names live in `editions`; tags are the shown machine's notable features.
    tags: list[str] = []
    for name, _group in rep.features:
        if name in TAG_FEATURES and name not in tags:
            tags.append(name)

    players_label = _plural(rep.players, "player") if rep.players else None
    summary_parts = [
        TYPE_LABELS.get(rep.type or ""),
        DISPLAY_LABELS.get(rep.display or ""),
        players_label,
    ]
    headline_parts = [rep.manufacturer, str(title.year) if title.year else None]

    facts: list[dict[str, str]] = []
    if years_ago := _years_ago(title.year, today):
        facts.append({"label": "Released", "value": years_ago})
    facts.append({"label": "Era", "value": ERA_LABELS[era]})
    position = dataset.manufacturer_position(title)
    if position and rep.manufacturer:
        index, total = position
        facts.append({"label": rep.manufacturer, "value": f"Title {index} of {total}"})
    same_year = [
        t for t in dataset.titles_by_year.get(title.year or 0, []) if t.group_id != title.group_id
    ]
    if title.year:
        facts.append(
            {"label": f"Class of {title.year}", "value": f"1 of {len(same_year) + 1} titles"}
        )
    if len(title.machines) > 1:
        facts.append({"label": "Editions", "value": _plural(len(title.machines), "variant")})

    anniversary = (
        _has_exact_date(rep)
        and rep.manufacture_date is not None
        and (rep.manufacture_date.month, rep.manufacture_date.day) == (today.month, today.day)
        and today.year > rep.manufacture_date.year
    )

    fun_fact = _fun_fact(
        title, anniversary=anniversary, today=today, position=position, same_year=len(same_year)
    )

    return {
        "machine": {
            "id": rep.opdb_id,
            "group_id": title.group_id,
            "name": title.name,
            "edition_name": rep.name,
            "short_name": title.short_name,
            "manufacturer": rep.manufacturer,
            "manufacturer_full": rep.manufacturer_full,
            "year": title.year,
            "release_label": _release_label(rep),
            "type_label": TYPE_LABELS.get(rep.type or ""),
            "display_label": DISPLAY_LABELS.get(rep.display or ""),
            "players": rep.players,
            "players_label": players_label,
            "era": era.value,
            "era_label": ERA_LABELS[era],
            "headline": " · ".join(p for p in headline_parts if p),
            "summary": " · ".join(p for p in summary_parts if p),
            "tags": tags,
            "ipdb_id": rep.ipdb_id,
            "anniversary": anniversary,
        },
        "images": {
            "backglass": _image_payload(_first_image(title, "backglass", rep)),
            "playfield": _image_payload(_first_image(title, "playfield", rep)),
            "cabinet": _image_payload(_first_image(title, "cabinet", rep)),
            "any": _image_payload(_any_image(title, rep)),
        },
        "editions": title.edition_list(rep),
        "credits": _credits(title, rep),
        "facts": facts,
        "fun_fact": fun_fact,
        "same_year": [
            {"name": t.name, "manufacturer": t.manufacturer} for t in same_year[:SAME_YEAR_LIMIT]
        ],
        "same_year_count": len(same_year),
        # Rendered on TRMNL with the built-in `qr_code` Liquid filter.
        "qr": {"url": page_url},
        "links": {"page": page_url, "opdb": opdb_url(rep)},
        "featured": {
            "label": ROTATION_LABELS.get(rotation, DEFAULT_LABEL),
            # Shown bottom-right in the title bar, in the viewer's own time zone.
            "updated_label": updated_label(local_now),
            "timezone": local_now.tzname(),
            "date": today.isoformat(),
            "date_label": f"{local_now:%A, %B} {today.day}",
            "date_short": f"{local_now:%b} {today.day}",
            "period": period,
            "rotation": rotation.value,
            "pool_size": pool_size,
            "filter_label": _filter_label(filters),
        },
        "source": {
            "name": "OPDB",
            "url": "https://opdb.org",
            "updated": (dataset.fetched_at.date().isoformat() if dataset.fetched_at else None),
        },
        "error": None,
    }


def _first_image(title: Title, kind: str, rep: Machine) -> Image | None:
    """The shown edition's photo, else a sibling edition's (CE/LE often have none)."""
    for machine in (rep, title.representative, *title.machines):
        if image := machine.image(kind):
            return image
    return None


def _any_image(title: Title, rep: Machine) -> Image | None:
    for machine in (rep, title.representative, *title.machines):
        if machine.images:
            return machine.image("backglass") or machine.images[0]
    return None


def _filter_label(filters: Filters) -> str | None:
    """Short human summary of the active filters, e.g. "Williams, Bally · 1990s"."""
    if filters.favorites:
        return "Favorites"
    parts: list[str] = []
    if filters.eras:
        parts.append(", ".join(ERA_LABELS[e] for e in sorted(filters.eras)))
    if filters.decades:
        parts.append(", ".join(f"{d}s" for d in sorted(filters.decades)))
    if filters.min_year and filters.max_year:
        parts.append(f"{filters.min_year}–{filters.max_year}")
    elif filters.min_year:
        parts.append(f"{filters.min_year}+")
    elif filters.max_year:
        parts.append(f"Up to {filters.max_year}")
    if filters.manufacturers:
        parts.append(", ".join(m.title() for m in filters.manufacturers))
    if filters.keywords:
        parts.append(", ".join(k.title() for k in filters.keywords))
    if filters.people:
        parts.append(", ".join(p.title() for p in filters.people))
    if len(parts) > 2:
        return "Custom selection"
    return " · ".join(parts) or None


def _fun_fact(
    title: Title,
    *,
    anniversary: bool,
    today: date,
    position: tuple[int, int] | None,
    same_year: int,
) -> str:
    rep = title.representative
    maker = rep.manufacturer or "its maker"
    if anniversary and rep.manufacture_date:
        return f"Happy birthday! {title.name} was released {_plural(today.year - rep.manufacture_date.year, 'year')} ago today."
    if position and position[0] == 1 and position[1] > 1:
        return f"The very first {maker} title in the database, ahead of {position[1] - 1} more."
    if position and position[0] == position[1] and position[1] > 1:
        return f"The newest of {position[1]} {maker} titles in the database."
    if title.short_name and title.short_name.lower() != title.name.lower():
        return f"Players call it {title.short_name}."
    if len(title.machines) > 1:
        if title.editions:
            return f"Built in {len(title.machines)} variants: {', '.join(title.editions)}."
        return f"Built in {len(title.machines)} variants."
    if same_year:
        return f"One of {same_year + 1} titles released in {title.year}."
    return f"Made by {rep.manufacturer_full or maker}."


def build_error(title: str, message: str) -> dict[str, Any]:
    return {"error": {"title": title, "message": message}}
