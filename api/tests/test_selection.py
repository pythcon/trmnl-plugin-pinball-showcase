from datetime import datetime
from itertools import pairwise

from pinball_showcase.dataset import Dataset, build_dataset
from pinball_showcase.selection import (
    Era,
    Filters,
    PickMemo,
    Rotation,
    candidate_pool,
    choose,
    matches,
    period_index,
    period_key,
    pick,
    shuffle_pick,
)
from tests.conftest import group, machine


def ids(titles) -> set[str]:
    return {t.group_id for t in titles}


def test_pick_is_deterministic(dataset: Dataset) -> None:
    pool = candidate_pool(dataset, Filters())
    assert pick(pool, 1000, Filters()) == pick(list(reversed(pool)), 1000, Filters())


def test_full_cycle_has_no_repeats(dataset: Dataset) -> None:
    pool = candidate_pool(dataset, Filters())
    n = len(pool)
    for cycle in range(3):
        shown = [pick(pool, cycle * n + i, Filters()).group_id for i in range(n)]
        assert sorted(shown) == sorted(ids(pool))


def test_never_shows_the_same_machine_twice_in_a_row(dataset: Dataset) -> None:
    for size in (2, 3, 4):
        pool = candidate_pool(dataset, Filters())[:size]
        shown = [pick(pool, i, Filters()).group_id for i in range(size * 40)]
        assert all(a != b for a, b in pairwise(shown)), size


def test_empty_pool_returns_none() -> None:
    assert pick([], 0, Filters()) is None


def test_multi_value_era_filter(dataset: Dataset) -> None:
    assert ids(candidate_pool(dataset, Filters(eras=frozenset({Era.ELECTRO_MECHANICAL})))) == {
        "GCCCC"
    }
    both = Filters(eras=frozenset({Era.ELECTRO_MECHANICAL, Era.MODERN}))
    assert ids(candidate_pool(dataset, both)) == {"GCCCC", "GBBBB"}


def test_categories_are_anded(dataset: Dataset) -> None:
    f = Filters(manufacturers=("williams", "stern"), decades=frozenset({1990}))
    assert ids(candidate_pool(dataset, f)) == {"GAAAA"}


def test_known_manufacturer_matches_exactly(export) -> None:
    export["entries"] += [
        group("GGGGG", "Flash"),
        machine(
            "GGGGG-M0001", "Flash", year=1979, maker="Stern Electronics", display="alphanumeric"
        ),
    ]
    dataset = build_dataset(export)
    stern = ids(candidate_pool(dataset, Filters(manufacturers=("stern",))))
    assert stern == {"GBBBB"}  # not Stern Electronics
    both = ids(candidate_pool(dataset, Filters(manufacturers=("stern", "stern electronics"))))
    assert both == {"GBBBB", "GGGGG"}
    # Free text that isn't a known name still matches as a substring.
    assert ids(candidate_pool(dataset, Filters(manufacturers=("electron",)))) == {"GGGGG"}
    no_stern = ids(candidate_pool(dataset, Filters(exclude_manufacturers=("stern",))))
    assert "GGGGG" in no_stern and "GBBBB" not in no_stern


def test_manufacturer_include_exclude(dataset: Dataset) -> None:
    afm = dataset.by_group["GDDDD"]
    assert matches(afm, Filters(manufacturers=("stern", "bally")))
    assert not matches(afm, Filters(manufacturers=("stern",)))
    assert not matches(afm, Filters(exclude_manufacturers=("bally",)))


def test_year_range_and_decades(dataset: Dataset) -> None:
    afm = dataset.by_group["GDDDD"]
    assert matches(afm, Filters(min_year=1990, max_year=1995))
    assert not matches(afm, Filters(min_year=1996))
    assert matches(afm, Filters(decades=frozenset({1950, 1990})))
    assert not matches(afm, Filters(decades=frozenset({1980})))


def test_display_players_features(dataset: Dataset) -> None:
    assert ids(candidate_pool(dataset, Filters(displays=frozenset({"reels"})))) == {"GCCCC"}
    assert len(candidate_pool(dataset, Filters(players=frozenset({4})))) == 4
    assert not candidate_pool(dataset, Filters(players=frozenset({6})))
    remakes = Filters(features=frozenset({"remake"}))
    assert ids(candidate_pool(dataset, remakes)) == {"GAAAA"}
    multi = Filters(features=frozenset({"multi_edition"}))
    assert ids(candidate_pool(dataset, multi)) == {"GAAAA", "GBBBB"}
    no_multi = Filters(exclude_features=frozenset({"multi_edition"}))
    assert ids(candidate_pool(dataset, no_multi)) == {"GCCCC", "GDDDD"}


def test_keywords_people_and_playfield(dataset: Dataset) -> None:
    assert ids(candidate_pool(dataset, Filters(keywords=("madness", "mars")))) == {
        "GAAAA",
        "GDDDD",
    }
    assert "GAAAA" not in ids(candidate_pool(dataset, Filters(exclude_keywords=("madness",))))
    assert ids(candidate_pool(dataset, Filters(people=("brian eddy",)))) == {"GAAAA"}
    assert ids(candidate_pool(dataset, Filters(require_playfield=True))) == {"GAAAA"}


def test_favorites_and_exclusions(dataset: Dataset) -> None:
    favs = Filters(favorites=("GDDDD", "GCCCC-M0001"))
    assert ids(candidate_pool(dataset, favs)) == {"GDDDD", "GCCCC"}
    assert "GDDDD" not in ids(candidate_pool(dataset, Filters(exclude_ids=("GDDDD-M0001",))))


def test_period_keys_and_indices() -> None:
    now = datetime(2026, 10, 5, 17, 42)
    assert period_key(now, Rotation.DAILY) == "2026-10-05"
    tomorrow = datetime(2026, 10, 6, 0, 0)
    assert period_index(tomorrow, Rotation.DAILY) == period_index(now, Rotation.DAILY) + 1
    # Schedules line up with the clock: 6h periods start at 00, 06, 12, 18.
    assert period_index(datetime(2026, 10, 5, 12, 0), Rotation.EVERY_6H) == period_index(
        now, Rotation.EVERY_6H
    )
    assert (
        period_index(datetime(2026, 10, 5, 18, 0), Rotation.EVERY_6H)
        == period_index(now, Rotation.EVERY_6H) + 1
    )
    assert period_index(tomorrow, Rotation.EVERY_1H) - period_index(now, Rotation.EVERY_1H) == 7


def test_refresh_rotation_follows_the_plugin_interval() -> None:
    a = datetime(2026, 10, 5, 10, 0)
    b = datetime(2026, 10, 5, 10, 14)
    c = datetime(2026, 10, 5, 10, 15)
    assert period_index(a, Rotation.REFRESH, 15) == period_index(b, Rotation.REFRESH, 15)
    assert period_index(c, Rotation.REFRESH, 15) == period_index(a, Rotation.REFRESH, 15) + 1
    # Missing or silly intervals are clamped (default 60 min, minimum 5).
    assert period_key(a, Rotation.REFRESH, None).startswith("60m-")
    assert period_key(a, Rotation.REFRESH, 1).startswith("5m-")


def test_shuffle_never_repeats_the_previous_machine(dataset: Dataset) -> None:
    pool = candidate_pool(dataset, Filters())
    for _ in range(50):
        last = shuffle_pick(pool).group_id
        nxt = shuffle_pick(pool, avoid=(last,))
        assert nxt.group_id != last
    # A one-machine pool still returns that machine.
    assert shuffle_pick(pool[:1], avoid=(pool[0].group_id,)) is pool[0]


def test_shuffle_ignores_the_memo(dataset: Dataset, tmp_path) -> None:
    memo = PickMemo(tmp_path / "picks.json")
    now = datetime(2026, 10, 5, 9)
    seen = {choose(dataset, Filters(), now, Rotation.SHUFFLE, memo)[0].group_id for _ in range(40)}
    assert len(seen) > 1


def test_rotation_aliases() -> None:
    from pinball_showcase.params import parse_rotation

    assert parse_rotation("hourly") is Rotation.EVERY_1H
    assert parse_rotation("12h") is Rotation.EVERY_12H
    assert parse_rotation("REFRESH") is Rotation.REFRESH
    assert parse_rotation("nonsense") is Rotation.DAILY


def test_filter_signature() -> None:
    assert Filters().signature == ""
    a = Filters(manufacturers=("bally", "williams"))
    b = Filters(manufacturers=("williams", "bally"))
    assert a.signature == b.signature
    assert a.signature != Filters(manufacturers=("bally",)).signature


def test_memo_keeps_pick_when_pool_changes(dataset: Dataset, tmp_path) -> None:
    memo = PickMemo(tmp_path / "picks.json")
    now = datetime(2026, 10, 5, 9)
    first, _ = choose(dataset, Filters(), now, Rotation.DAILY, memo)
    # Exclude a different title: without the memo the shuffle could move.
    other = next(t for t in dataset.showcase_titles if t is not first)
    again, size = choose(dataset, Filters(), now, Rotation.DAILY, memo)
    assert again is first
    # The memo is persisted and reloaded.
    assert PickMemo(tmp_path / "picks.json").get("daily:2026-10-05", Filters()) == first.group_id
    assert other is not first and size == 4


def test_memo_is_ignored_when_title_leaves_pool(dataset: Dataset, tmp_path) -> None:
    memo = PickMemo(tmp_path / "picks.json")
    now = datetime(2026, 10, 5, 9)
    first, _ = choose(dataset, Filters(), now, Rotation.DAILY, memo)
    memo.put("daily:2026-10-05", Filters(), "GEEEE")  # not showcase-ready
    again, _ = choose(dataset, Filters(), now, Rotation.DAILY, memo)
    assert again is first
