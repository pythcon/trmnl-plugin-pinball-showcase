"""Type-ahead search over every title and edition in the dataset.

Every word of the query must prefix-match a word of the title (name, short name,
edition label, maker or year), so "med mad", "mm", "potter ce" and "bally 1993" all
work. Results are one per title; when a query word names an edition ("ce", "premium",
"arcade") that edition is the result instead of the title's default.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass

from .dataset import Dataset, Title
from .models import Image, Machine

_NON_WORD = re.compile(r"[^0-9a-z]+")
MAX_RESULTS = 20


def normalize(text: str) -> str:
    """Lowercase, accents stripped, punctuation to spaces: "Pokémon's" -> "pokemon s"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_WORD.sub(" ", plain.replace("&", " and ")).strip()


def _words(text: str | None) -> tuple[str, ...]:
    return tuple(normalize(text).split()) if text else ()


@dataclass(frozen=True, slots=True)
class _Edition:
    machine: Machine
    label: str | None
    label_words: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Entry:
    title: Title
    name: str  # normalized
    name_words: tuple[str, ...]
    short_words: tuple[str, ...]
    maker_words: tuple[str, ...]
    year: str
    editions: tuple[_Edition, ...]


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: Title
    machine: Machine
    edition_label: str | None
    image: Image | None
    image_borrowed: bool

    @property
    def opdb_id(self) -> str:
        return self.machine.opdb_id


class SearchIndex:
    """Built once per dataset; each query is a linear scan (~1,600 titles, <5 ms)."""

    def __init__(self, dataset: Dataset) -> None:
        entries: list[_Entry] = []
        for title in dataset.titles:
            if not title.representative.physical:
                continue
            # Both forms are searchable: "potter ce" and "potter collector" both work.
            labels = title.edition_labels()
            short = title.edition_labels(short=True)
            editions = tuple(
                _Edition(
                    m,
                    labels.get(m.opdb_id),
                    _words(labels.get(m.opdb_id)) + _words(short.get(m.opdb_id)),
                )
                for m in title.versions
            )
            makers = {w for m in title.versions for w in _words(m.manufacturer)}
            makers |= {w for m in title.versions for w in _words(m.manufacturer_full)}
            # Initials of multi-word makers, so "jjp" finds Jersey Jack Pinball.
            makers |= {
                "".join(w[0] for w in words)
                for m in title.versions
                if len(words := _words(m.manufacturer)) > 1
            }
            entries.append(
                _Entry(
                    title=title,
                    name=normalize(title.name),
                    name_words=_words(title.name),
                    short_words=_words(title.short_name),
                    maker_words=tuple(sorted(makers)),
                    year=str(title.year or ""),
                    editions=editions,
                )
            )
        self._entries = entries

    def __len__(self) -> int:
        return len(self._entries)

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        q = normalize(query)
        tokens = q.split()
        if not tokens:
            return []
        limit = max(1, min(limit, MAX_RESULTS))
        scored: list[tuple[float, str, SearchResult]] = []
        for entry in self._entries:
            match = _score(entry, q, tokens)
            if match is None:
                continue
            score, edition = match
            scored.append((-score, entry.name, _result(entry.title, edition)))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [result for _, _, result in scored[:limit]]


_cache_lock = threading.Lock()
_cache: tuple[Dataset, SearchIndex] | None = None


def index_for(dataset: Dataset) -> SearchIndex:
    """The index for this dataset, rebuilt once after each daily refresh swaps it."""
    global _cache
    with _cache_lock:
        if _cache is None or _cache[0] is not dataset:
            _cache = (dataset, SearchIndex(dataset))
        return _cache[1]


def result_payload(result: SearchResult) -> dict[str, object]:
    """JSON shape shared by the API and the site's type-ahead."""
    return {
        "id": result.opdb_id,
        "url": f"/m/{result.opdb_id}",
        "name": result.title.name,
        "edition_label": result.edition_label,
        "edition_count": len(result.title.versions),
        "manufacturer": result.machine.manufacturer or result.title.manufacturer,
        "year": result.machine.year or result.title.year,
        "image": (result.image.url("medium") or result.image.url("large"))
        if result.image
        else None,
        "image_borrowed": result.image_borrowed,
    }


def _prefix_hit(token: str, words: tuple[str, ...]) -> bool:
    return any(word.startswith(token) for word in words)


def _score(entry: _Entry, q: str, tokens: list[str]) -> tuple[float, _Edition | None] | None:
    """Relevance of a title, and the edition a query word named (if any)."""
    score = 0.0
    named: _Edition | None = None
    for token in tokens:
        if _prefix_hit(token, entry.name_words):
            score += 10
        elif token in entry.short_words:
            score += 9
        elif edition := next(
            (e for e in entry.editions if _prefix_hit(token, e.label_words)), None
        ):
            named = named or edition
            score += 7
        elif _prefix_hit(token, entry.maker_words) or (
            entry.year.startswith(token) and token.isdigit()
        ):
            score += 4
        else:
            return None
    # Whole-name matches first: exact, then prefix, then the start of any word.
    if entry.name == q:
        score += 60
    elif entry.name.startswith(q):
        score += 40
    elif f" {q}" in f" {entry.name}":
        score += 20
    if q in entry.short_words:
        score += 30
    # Gentle tie-breakers: games with art, then shorter names.
    if entry.title.representative.images:
        score += 2
    score -= len(entry.name) / 100
    return score, named


def _result(title: Title, edition: _Edition | None) -> SearchResult:
    machine = edition.machine if edition else title.representative
    badge = title.badge(machine)
    image, borrowed = _thumbnail(title, machine)
    return SearchResult(
        title=title,
        machine=machine,
        edition_label=badge[0] if badge else None,
        image=image,
        image_borrowed=borrowed,
    )


def _thumbnail(title: Title, machine: Machine) -> tuple[Image | None, bool]:
    """The edition's own backglass (or any photo), else the title's."""
    own = machine.image("backglass") or (machine.images[0] if machine.images else None)
    if own:
        return own, False
    for other in (title.representative, *title.versions):
        if image := other.image("backglass") or (other.images[0] if other.images else None):
            return image, True
    return None, False
