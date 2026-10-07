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

from .editions import STANDARD_LONG, STANDARD_SHORT, expand, is_edition_suffix, shorten
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


def _base_label(title_name: str, machine: Machine) -> tuple[str, str]:
    """(long, short) edition label from the machine's name; see editions.py."""
    if match := _PAREN_SUFFIX.search(machine.name):
        return expand(match.group(1)), shorten(match.group(1))
    name = machine.name.strip()
    # "Centaur" under "Centaur (Inder)": the game's own name, without its qualifier.
    core = _PAREN_SUFFIX.sub("", title_name).strip()
    if name.casefold() in (title_name.strip().casefold(), core.casefold()):
        return STANDARD_LONG, STANDARD_SHORT
    # "Fire! Champagne Edition" under "Fire!" -> "Champagne Edition" / "Champagne"
    if name.casefold().startswith(title_name.strip().casefold() + " "):
        rest = name[len(title_name.strip()) :].strip()
        return expand(rest), shorten(rest)
    return name, name


def clean_title_name(name: str) -> str:
    """Drop an edition OPDB baked into a game's name: "The Texas Chainsaw Massacre (SE)",
    "Star Wars (Home Edition)". Other parentheticals stay ("Centaur (Inder)")."""
    if (match := _PAREN_SUFFIX.search(name)) and is_edition_suffix(match.group(1)):
        return name[: match.start()].strip() or name
    return name


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

    @property
    def versions(self) -> tuple[Machine, ...]:
        """Real editions: every machine and alias, minus umbrella entries.

        OPDB sometimes files a title's editions as aliases of one bare machine that has
        no photos itself ("Harry Potter" with Arcade, Wizard and CE aliases). That bare
        entry isn't an edition anyone can buy, so it's left out.
        """
        return tuple(m for m in self.machines if not self._is_umbrella(m))

    def _is_umbrella(self, machine: Machine) -> bool:
        return (
            machine.alias_of is None
            and not machine.images
            and any(m.alias_of == machine.opdb_id and m.images for m in self.machines)
        )

    def label_for(self, machine: Machine) -> str | None:
        """Long, unique edition label; None for umbrella entries (not editions)."""
        return self.edition_labels().get(machine.opdb_id)

    def edition_labels(self, short: bool = False) -> dict[str, str]:
        """Edition label per id, distinct within the title, long or short form.

        - a parenthesised suffix: "Harry Potter (CE)" -> "Collector's Edition" / "CE"
        - else what sets the name apart: "Olympics" in "Super Star / Olympics",
          "Fire! Champagne Edition" -> "Champagne Edition" / "Champagne"
        - else "Standard Edition" / "Standard"
        Labels that still collide get the maker, then the year: "Standard Edition (Gottlieb)".
        """
        return {k: pair[1 if short else 0] for k, pair in self._labels().items()}

    def _labels(self) -> dict[str, tuple[str, str]]:
        base = {m.opdb_id: _base_label(self.name, m) for m in self.versions}
        by_label: dict[str, list[Machine]] = defaultdict(list)
        for machine in self.versions:
            by_label[base[machine.opdb_id][0]].append(machine)
        labels = dict(base)
        for machines in by_label.values():
            if len(machines) < 2:
                continue
            for extra in (lambda m: m.manufacturer, lambda m: m.year):
                values = [extra(m) for m in machines]
                if all(values) and len(set(values)) == len(values):
                    for machine, value in zip(machines, values, strict=True):
                        long, short = base[machine.opdb_id]
                        labels[machine.opdb_id] = (f"{long} ({value})", f"{short} ({value})")
                    break
            else:
                for i, machine in enumerate(machines[1:], start=2):
                    long, short = base[machine.opdb_id]
                    labels[machine.opdb_id] = (f"{long} #{i}", f"{short} #{i}")
        return labels

    def badge(self, machine: Machine) -> tuple[str, str] | None:
        """(long, short) label to show for this edition, or None for no badge.

        Shown when the title has several editions, or when its only edition is a named
        one (a Home Edition, a 60th Anniversary LE); a plain single model gets none.
        """
        pair = self._labels().get(machine.opdb_id)
        if pair is None:
            return None
        if len(self.versions) > 1 or pair[0] != STANDARD_LONG:
            return pair
        return None

    def edition_list(self, shown: Machine) -> list[dict[str, Any]]:
        """Every version of the title, long and short labels, the shown one marked."""
        labels = self._labels()
        return [
            {
                "label": labels[m.opdb_id][0],
                "short": labels[m.opdb_id][1],
                "id": m.opdb_id,
                "shown": m.opdb_id == shown.opdb_id,
            }
            for m in self.versions
        ]

    @property
    def editions(self) -> list[str]:
        """Edition names derived from machine names, e.g. ["Pro", "Premium/LE"]."""
        labels = self._labels()
        names: list[str] = []
        for machine in self.versions:
            label = labels[machine.opdb_id][0]
            if _PAREN_SUFFIX.search(machine.name) and label not in names:
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
        """The exact edition for a machine or alias id; None for a bare group id."""
        parts = opdb_id.strip().split("-")
        for size in (3, 2):
            if len(parts) < size:
                continue
            edition_id = "-".join(parts[:size])
            title = self.by_machine.get(edition_id)
            if title is not None:
                return next(m for m in title.machines if m.opdb_id == edition_id)
        return None

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
            # Aliases are full editions of a machine (Harry Potter's CE, Pirates' LE).
            parent = entry.get("opdbMachine") or "-".join(entry["opdbId"].split("-")[:2])
            machine = parse_machine(entry, alias_of=parent)
            machines_by_group[machine.group_id].append(machine)
            aliases_by_group[machine.group_id].append(entry["name"])

    titles: list[Title] = []
    for group_id, machines in machines_by_group.items():
        machines.sort(key=_representative_key)
        rep = machines[0]
        name, short_name = group_names.get(group_id, (None, None))
        name = clean_title_name(name) if name else name
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
