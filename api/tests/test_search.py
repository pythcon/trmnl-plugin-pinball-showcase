"""Type-ahead search: matching, ranking and edition targeting."""

from __future__ import annotations

from pinball_showcase.dataset import Dataset
from pinball_showcase.search import SearchIndex, index_for, normalize


def names(dataset: Dataset, query: str) -> list[tuple[str, str | None]]:
    return [(r.title.name, r.edition_label) for r in SearchIndex(dataset).search(query)]


def test_normalize_folds_case_accents_and_punctuation() -> None:
    assert normalize("Pokémon's  ROCK & Roll!") == "pokemon s rock and roll"


def test_every_word_must_prefix_match(dataset: Dataset) -> None:
    assert names(dataset, "med mad") == [("Medieval Madness", "Standard")]
    assert names(dataset, "madness medieval") == [("Medieval Madness", "Standard")]
    assert names(dataset, "medieval zebra") == []
    assert names(dataset, "") == []


def test_short_names_makers_and_years(dataset: Dataset) -> None:
    assert names(dataset, "mm")[0][0] == "Medieval Madness"
    assert {n for n, _ in names(dataset, "gottlieb")} == {"Gold Star"}
    assert {n for n, _ in names(dataset, "1954")} == {"Gold Star"}


def test_naming_an_edition_returns_that_edition(dataset: Dataset) -> None:
    assert names(dataset, "godzilla premium") == [("Godzilla", "Premium/LE")]
    assert names(dataset, "godzilla") == [("Godzilla", "Pro")]
    result = SearchIndex(dataset).search("godzilla premium")[0]
    # The Premium/LE has no photos: the thumbnail is the Pro's, flagged as borrowed.
    assert result.image is not None and result.image_borrowed is True


def test_exact_and_prefix_matches_rank_first(dataset: Dataset) -> None:
    assert names(dataset, "attack")[0][0] == "Attack from Mars"


def test_virtual_machines_are_not_searchable(dataset: Dataset) -> None:
    assert names(dataset, "virtual") == []


def test_index_is_cached_per_dataset(dataset: Dataset) -> None:
    assert index_for(dataset) is index_for(dataset)
