"""Parse the OPDB export into showcase-ready titles plus lookup indices.

OPDB models a pinball title as a *machine group* (e.g. "Godzilla", 2021) holding one or
more *machines* (Pro, Premium, LE...). The showcase features titles, not individual
editions, so a day never lands on "Godzilla (Pro)" and then "Godzilla (LE)" the next.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .models import Machine, parse_machine

# Lower rank = better representative for a title.
_EDITION_RANK = {
    "": 0,
    "Pro edition": 1,
    "Premium edition": 2,
    "Limited edition": 3,
    "Remake": 4,
    "Vault edition": 5,
    "Export edition": 6,
    "Home model": 7,
    "Converted game": 8,
    "Conversion kit": 9,
}

_PAREN_SUFFIX = re.compile(r"\s*\(([^)]*)\)\s*$")


def _edition_label(text: str) -> str:
    """ "Remake Special Edition" -> "Remake Special"; "Edition" alone stays."""
    trimmed = re.sub(r"\s+edition$", "", text.strip(), flags=re.IGNORECASE)
    return trimmed or text.strip()


@dataclass(frozen=True, slots=True)
class Title:
    group_id: str
    name: str
    short_name: str | None
    representative: Machine
    machines: tuple[Machine, ...]
    # Alternate names and limited runs OPDB lists as aliases ("The Beatles (Platinum)").
    aliases: tuple[str, ...] = ()

    @property
    def year(self) -> int | None:
        return self.representative.year

    @property
    def manufacturer(self) -> str | None:
        return self.representative.manufacturer

    def edition_list(self, shown: Machine) -> list[dict[str, Any]]:
        """Every version of the title, OPDB editions first, then alias-only versions.

        Labels come from the parenthesised suffix ("Pro", "Premium/LE"); an edition
        without one is the "Standard" model.
        """
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for machine in self.machines:
            match = _PAREN_SUFFIX.search(machine.name)
            label = _edition_label(match.group(1)) if match else "Standard"
            if label in seen:
                continue
            seen.add(label)
            entries.append(
                {"label": label, "id": machine.opdb_id, "shown": machine.opdb_id == shown.opdb_id}
            )
        for alias in self.aliases:
            match = _PAREN_SUFFIX.search(alias)
            label = _edition_label(match.group(1)) if match else None
            if label and label not in seen:
                seen.add(label)
                entries.append({"label": label, "id": None, "shown": False})
        return entries

    @property
    def editions(self) -> list[str]:
        """Edition names derived from machine names, e.g. ["Pro", "Premium/LE"]."""
        names: list[str] = []
        for machine in self.machines:
            match = _PAREN_SUFFIX.search(machine.name)
            label = match.group(1) if match else None
            if label and label not in names:
                names.append(label)
        return names


@dataclass(slots=True)
class Dataset:
    titles: list[Title]
    by_group: dict[str, Title]
    by_machine: dict[str, Title]
    titles_by_year: dict[int, list[Title]]
    titles_by_manufacturer: dict[str, list[Title]]  # chronological
    entry_count: int
    source_last_modified: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def showcase_titles(self) -> list[Title]:
        return [t for t in self.titles if is_showcase_ready(t)]

    def lookup(self, opdb_id: str) -> Title | None:
        opdb_id = opdb_id.strip()
        if opdb_id in self.by_machine:
            return self.by_machine[opdb_id]
        # Accept a group id, or an alias id like G0l8P-M85d9-A1ZNY.
        parts = opdb_id.split("-")
        if len(parts) >= 2 and "-".join(parts[:2]) in self.by_machine:
            return self.by_machine["-".join(parts[:2])]
        return self.by_group.get(parts[0])

    def lookup_edition(self, opdb_id: str) -> Machine | None:
        """The exact edition for a machine (or alias) id; None for a bare group id."""
        parts = opdb_id.strip().split("-")
        if len(parts) < 2:
            return None
        machine_id = "-".join(parts[:2])
        title = self.by_machine.get(machine_id)
        if title is None:
            return None
        return next((m for m in title.machines if m.opdb_id == machine_id), None)

    def manufacturer_position(self, title: Title) -> tuple[int, int] | None:
        """1-based position of a title in its manufacturer's catalogue, and the total."""
        if not title.manufacturer:
            return None
        catalogue = self.titles_by_manufacturer.get(title.manufacturer, [])
        for i, other in enumerate(catalogue, start=1):
            if other.group_id == title.group_id:
                return i, len(catalogue)
        return None


def is_showcase_ready(title: Title) -> bool:
    rep = title.representative
    return rep.physical and bool(rep.images)


def _representative_key(machine: Machine) -> tuple:
    edition_rank = min(
        (_EDITION_RANK.get(name, 5) for name in machine.edition_features),
        default=0,
    )
    return (
        0 if machine.has_backglass else 1,
        0 if machine.images else 1,
        0 if machine.physical else 1,
        edition_rank,
        machine.manufacture_date or datetime.max.date(),
        machine.opdb_id,
    )


def _date_key(title: Title) -> tuple:
    rep = title.representative
    return (rep.manufacture_date or datetime.max.date(), title.name, title.group_id)


def build_dataset(raw: dict[str, Any], *, source_last_modified: str | None = None) -> Dataset:
    entries = raw.get("entries")
    if not isinstance(entries, list):
        raise ValueError("OPDB export is missing the 'entries' list")

    group_names: dict[str, tuple[str, str | None]] = {}
    machines_by_group: dict[str, list[Machine]] = defaultdict(list)
    aliases_by_group: dict[str, list[str]] = defaultdict(list)

    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("opdbId"):
            continue
        kind = entry.get("entryType")
        if kind == "machineGroup":
            group_names[entry["opdbId"]] = (
                entry.get("name") or entry["opdbId"],
                entry.get("shortName"),
            )
        elif kind == "machine":
            machine = parse_machine(entry)
            machines_by_group[machine.group_id].append(machine)
        elif kind == "alias" and entry.get("name"):
            # Alternate names / limited runs; lookups resolve alias ids via their machine id.
            group_id = entry.get("opdbGroup") or entry["opdbId"].split("-")[0]
            aliases_by_group[group_id].append(entry["name"])

    titles: list[Title] = []
    for group_id, machines in machines_by_group.items():
        machines.sort(key=_representative_key)
        rep = machines[0]
        name, short_name = group_names.get(group_id, (None, None))
        if not name:
            name = _PAREN_SUFFIX.sub("", rep.name) or rep.name
        titles.append(
            Title(
                group_id=group_id,
                name=name,
                short_name=short_name or rep.short_name,
                representative=rep,
                aliases=tuple(dict.fromkeys(aliases_by_group.get(group_id, []))),
                machines=tuple(
                    sorted(
                        machines,
                        key=lambda m: (m.manufacture_date or datetime.max.date(), m.opdb_id),
                    )
                ),
            )
        )
    titles.sort(key=lambda t: t.group_id)

    by_machine = {m.opdb_id: t for t in titles for m in t.machines}
    titles_by_year: dict[int, list[Title]] = defaultdict(list)
    titles_by_manufacturer: dict[str, list[Title]] = defaultdict(list)
    for title in titles:
        if not title.representative.physical:
            continue
        if title.year:
            titles_by_year[title.year].append(title)
        if title.manufacturer:
            titles_by_manufacturer[title.manufacturer].append(title)
    for bucket in (*titles_by_year.values(), *titles_by_manufacturer.values()):
        bucket.sort(key=_date_key)

    return Dataset(
        titles=titles,
        by_group={t.group_id: t for t in titles},
        by_machine=by_machine,
        titles_by_year=dict(titles_by_year),
        titles_by_manufacturer=dict(titles_by_manufacturer),
        entry_count=len(entries),
        source_last_modified=source_last_modified,
    )
