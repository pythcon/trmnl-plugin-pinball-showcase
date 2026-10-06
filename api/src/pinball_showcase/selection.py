"""Filter the catalogue and pick the featured title for a rotation period.

Filters: every category accepts any number of values. Values inside a category are OR'd
("Williams or Bally"), categories are AND'd ("Williams or Bally" *and* "1990s").

Picking: the filtered pool is shuffled with a seed derived from the filters and the
current *cycle*, then walked one title per rotation period. Every title in the pool is
shown once before any repeats, which matters for small pools such as a favourites list.
Picks are memoised per period (see ``PickMemo``) so a mid-day dataset refresh never
swaps the machine that is already on screen.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from .dataset import Dataset, Title


class Era(StrEnum):
    ELECTRO_MECHANICAL = "em"
    EARLY_SOLID_STATE = "early_ss"
    DMD = "dmd"
    MODERN = "modern"


ERA_LABELS = {
    Era.ELECTRO_MECHANICAL: "Electro-mechanical",
    Era.EARLY_SOLID_STATE: "Early solid state",
    Era.DMD: "Dot matrix era",
    Era.MODERN: "Modern LCD era",
}
# Convenience aliases accepted by the API.
ERA_ALIASES = {"ss": {Era.EARLY_SOLID_STATE, Era.DMD, Era.MODERN}, "all": set()}

DISPLAYS = {"reels", "alphanumeric", "lights", "dmd", "lcd", "cga"}

# Filter key -> OPDB feature name.
FEATURES = {
    "widebody": "Widebody",
    "cocktail": "Cocktail table",
    "add_a_ball": "Add-a-ball",
    "replay": "Replay",
    "head_to_head": "Head-to-head play",
    "pro": "Pro edition",
    "premium": "Premium edition",
    "limited": "Limited edition",
    "remake": "Remake",
    "vault": "Vault edition",
    "home": "Home model",
    "export": "Export edition",
    "conversion": "Conversion kit",
}
# Pseudo-feature: titles released in more than one edition.
MULTI_EDITION = "multi_edition"


class Rotation(StrEnum):
    DAILY = "daily"  # midnight in the viewer's time zone
    EVERY_1H = "1h"  # on a schedule, aligned to the clock
    EVERY_2H = "2h"
    EVERY_3H = "3h"
    EVERY_6H = "6h"
    EVERY_12H = "12h"
    REFRESH = "refresh"  # every TRMNL refresh: period = the plugin's refresh interval
    SHUFFLE = "shuffle"  # random on every request, never the previous machine


ROTATION_ALIASES = {
    "hourly": Rotation.EVERY_1H,
    "every": Rotation.REFRESH,
    "random": Rotation.SHUFFLE,
}
ROTATION_MINUTES = {
    Rotation.DAILY: 24 * 60,
    Rotation.EVERY_1H: 60,
    Rotation.EVERY_2H: 120,
    Rotation.EVERY_3H: 180,
    Rotation.EVERY_6H: 360,
    Rotation.EVERY_12H: 720,
}
DEFAULT_REFRESH_MINUTES = 60
MIN_REFRESH_MINUTES = 5


def period_minutes(rotation: Rotation, interval: int | None = None) -> int:
    """Length of one rotation period. REFRESH uses the plugin's refresh interval."""
    if rotation == Rotation.REFRESH:
        return max(MIN_REFRESH_MINUTES, min(24 * 60, interval or DEFAULT_REFRESH_MINUTES))
    return ROTATION_MINUTES.get(rotation, 24 * 60)


EPOCH = date(2024, 1, 1)


@dataclass(frozen=True, slots=True)
class Filters:
    eras: frozenset[Era] = frozenset()
    decades: frozenset[int] = frozenset()  # 1970 means 1970-1979
    min_year: int | None = None
    max_year: int | None = None
    manufacturers: tuple[str, ...] = ()
    exclude_manufacturers: tuple[str, ...] = ()
    displays: frozenset[str] = frozenset()
    players: frozenset[int] = frozenset()
    features: frozenset[str] = frozenset()
    exclude_features: frozenset[str] = frozenset()
    keywords: tuple[str, ...] = ()  # matched against title names ("theme" search)
    exclude_keywords: tuple[str, ...] = ()
    people: tuple[str, ...] = ()  # designers, artists, coders, composers...
    favorites: tuple[str, ...] = ()  # OPDB ids; restricts the pool to these titles
    exclude_ids: tuple[str, ...] = ()
    require_playfield: bool = False

    @property
    def is_empty(self) -> bool:
        return self == Filters()

    @property
    def signature(self) -> str:
        """Canonical form folded into the shuffle seed so different filters differ."""
        if self.is_empty:
            return ""
        parts = {
            "era": sorted(e.value for e in self.eras),
            "dec": sorted(self.decades),
            "yr": [self.min_year, self.max_year],
            "mfr": sorted(self.manufacturers),
            "xmfr": sorted(self.exclude_manufacturers),
            "dsp": sorted(self.displays),
            "ply": sorted(self.players),
            "ftr": sorted(self.features),
            "xftr": sorted(self.exclude_features),
            "kw": sorted(self.keywords),
            "xkw": sorted(self.exclude_keywords),
            "ppl": sorted(self.people),
            "fav": sorted(self.favorites),
            "xid": sorted(self.exclude_ids),
            "pf": self.require_playfield,
        }
        return json.dumps(parts, separators=(",", ":"))


def title_era(title: Title) -> Era:
    rep = title.representative
    if rep.type in ("em", "me"):
        return Era.ELECTRO_MECHANICAL
    if rep.display == "lcd":
        return Era.MODERN
    if rep.display == "dmd":
        return Era.DMD
    return Era.EARLY_SOLID_STATE


def title_features(title: Title) -> set[str]:
    names = {name for m in title.machines for name, _ in m.features}
    keys = {key for key, name in FEATURES.items() if name in names}
    if len(title.versions) > 1:
        keys.add(MULTI_EDITION)
    return keys


def _contains_any(haystack: str, needles: Iterable[str]) -> bool:
    return any(n in haystack for n in needles)


def _id_matches(title: Title, ids: Iterable[str]) -> bool:
    for raw in ids:
        group = raw.split("-")[0]
        if group == title.group_id:
            return True
    return False


def _maker_matches(names: set[str], wanted: Iterable[str], known: frozenset[str]) -> bool:
    """A known manufacturer name ("stern") matches exactly, so picking Stern from the list
    doesn't also pull in Stern Electronics. Anything else ("jersey") matches as a substring."""
    joined = " ".join(names)
    return any(w in names if w in known else w in joined for w in wanted)


def known_manufacturers(dataset: Dataset) -> frozenset[str]:
    names: set[str] = set()
    for maker, titles in dataset.titles_by_manufacturer.items():
        names.add(maker.lower())
        if full := titles[0].representative.manufacturer_full:
            names.add(full.lower())
    return frozenset(names)


def matches(title: Title, f: Filters, known_makers: frozenset[str] = frozenset()) -> bool:
    rep = title.representative
    year = title.year

    if f.favorites and not _id_matches(title, f.favorites):
        return False
    if f.exclude_ids and _id_matches(title, f.exclude_ids):
        return False
    if f.eras and title_era(title) not in f.eras:
        return False
    if f.decades and (not year or year // 10 * 10 not in f.decades):
        return False
    if f.min_year and (not year or year < f.min_year):
        return False
    if f.max_year and (not year or year > f.max_year):
        return False

    if f.manufacturers or f.exclude_manufacturers:
        makers = {n.lower() for n in (rep.manufacturer, rep.manufacturer_full) if n}
        if f.manufacturers and not _maker_matches(makers, f.manufacturers, known_makers):
            return False
        if f.exclude_manufacturers and _maker_matches(
            makers, f.exclude_manufacturers, known_makers
        ):
            return False

    if f.displays and rep.display not in f.displays:
        return False
    if f.players and rep.players not in f.players:
        return False

    if f.features or f.exclude_features:
        have = title_features(title)
        if f.features and not (have & f.features):
            return False
        if f.exclude_features and have & f.exclude_features:
            return False

    if f.keywords or f.exclude_keywords:
        names = " ".join(
            [title.name, title.short_name or "", *(m.name for m in title.machines)]
        ).lower()
        if f.keywords and not _contains_any(names, f.keywords):
            return False
        if f.exclude_keywords and _contains_any(names, f.exclude_keywords):
            return False

    if f.people:
        credited = " | ".join(p.name for m in title.machines for p in m.people).lower()
        if not _contains_any(credited, f.people):
            return False

    return not (f.require_playfield and not any(m.image("playfield") for m in title.machines))


def candidate_pool(dataset: Dataset, filters: Filters) -> list[Title]:
    known = (
        known_manufacturers(dataset)
        if filters.manufacturers or filters.exclude_manufacturers
        else frozenset()
    )
    return [t for t in dataset.showcase_titles if matches(t, filters, known)]


def period_index(local_now: datetime, rotation: Rotation, interval: int | None = None) -> int:
    """Number of whole rotation periods since the epoch, counted in local wall-clock time."""
    minutes = (local_now.date() - EPOCH).days * 1440 + local_now.hour * 60 + local_now.minute
    return minutes // period_minutes(rotation, interval)


def period_key(local_now: datetime, rotation: Rotation, interval: int | None = None) -> str:
    if rotation == Rotation.DAILY:
        return local_now.date().isoformat()
    minutes = period_minutes(rotation, interval)
    index = period_index(local_now, rotation, interval)
    return f"{minutes}m-{index}"


def _rank(seed: str, group_id: str) -> bytes:
    return hashlib.sha256(f"{seed}#{group_id}".encode()).digest()


def _cycle_order(pool: list[Title], cycle: int, filters: Filters) -> list[Title]:
    seed = f"{filters.signature}|cycle{cycle}"
    return sorted(pool, key=lambda t: _rank(seed, t.group_id))


def pick(pool: list[Title], index: int, filters: Filters) -> Title | None:
    """Title for period ``index``: walk a seeded shuffle of the pool, one per period.

    Each cycle is a fresh shuffle of the whole pool, so nothing repeats within a cycle.
    Where one cycle ends and the next begins, the first two titles of the new cycle are
    swapped if needed so the same machine never shows twice in a row.
    """
    if not pool:
        return None
    n = len(pool)
    cycle, position = divmod(index, n)
    if n <= 2:  # nothing to shuffle; alternate in a stable order
        return sorted(pool, key=lambda t: t.group_id)[index % n]
    order = _cycle_order(pool, cycle, filters)
    if cycle > 0 and order[0] is _cycle_order(pool, cycle - 1, filters)[-1]:
        order[0], order[1] = order[1], order[0]
    return order[position]


class PickMemo:
    """Remembers which title was shown for (period, filters), persisted to disk.

    Keeps the on-screen machine stable for the whole period even if the dataset is
    refreshed (and the pool changes) part-way through it.
    """

    def __init__(self, path: Path | None, max_entries: int = 20_000) -> None:
        self.path = path
        self.max_entries = max_entries
        self._entries: OrderedDict[str, str] = OrderedDict()
        if path and path.exists():
            try:
                self._entries = OrderedDict(json.loads(path.read_text()))
            except (OSError, ValueError):
                self._entries = OrderedDict()

    @staticmethod
    def key(period: str, filters: Filters) -> str:
        digest = hashlib.sha256(filters.signature.encode()).hexdigest()[:16]
        return f"{period}|{digest}"

    def get(self, period: str, filters: Filters) -> str | None:
        return self._entries.get(self.key(period, filters))

    def put(self, period: str, filters: Filters, group_id: str) -> None:
        key = self.key(period, filters)
        if self._entries.get(key) == group_id:
            return
        self._entries[key] = group_id
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
        self._save()

    def _save(self) -> None:
        if not self.path:
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._entries))
        os.replace(tmp, self.path)


def choose(
    dataset: Dataset,
    filters: Filters,
    local_now: datetime,
    rotation: Rotation,
    memo: PickMemo | None = None,
    *,
    interval: int | None = None,
    avoid: tuple[str, ...] = (),
) -> tuple[Title | None, int]:
    """Featured title for the current period (or a shuffle pick) plus the pool size."""
    pool = candidate_pool(dataset, filters)
    if rotation == Rotation.SHUFFLE:
        return shuffle_pick(pool, avoid), len(pool)

    period = f"{rotation.value}:{period_key(local_now, rotation, interval)}"
    if memo and (remembered := memo.get(period, filters)):
        title = dataset.by_group.get(remembered)
        if title is not None and any(t.group_id == remembered for t in pool):
            return title, len(pool)
    title = pick(pool, period_index(local_now, rotation, interval), filters)
    if memo and title is not None:
        memo.put(period, filters, title.group_id)
    return title, len(pool)


def shuffle_pick(pool: list[Title], avoid: tuple[str, ...] = ()) -> Title | None:
    """Random title, skipping the ones just shown (by group or machine id) when possible."""
    if not pool:
        return None
    avoid_groups = {a.split("-")[0] for a in avoid if a}
    fresh = [t for t in pool if t.group_id not in avoid_groups] or pool
    return secrets.choice(fresh)
