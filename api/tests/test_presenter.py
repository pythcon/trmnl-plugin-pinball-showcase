from datetime import datetime

from pinball_showcase.dataset import Dataset
from pinball_showcase.presenter import build_showcase
from pinball_showcase.selection import Filters, Rotation


def render(dataset: Dataset, group_id: str, now: datetime) -> dict:
    return build_showcase(
        dataset,
        dataset.by_group[group_id],
        local_now=now,
        rotation=Rotation.DAILY,
        filters=Filters(),
        pool_size=4,
        period=now.date().isoformat(),
        site_url="https://pinball-showcase.trmnlplugins.com",
    )


def test_payload_shape(dataset: Dataset) -> None:
    p = render(dataset, "GAAAA", datetime(2026, 10, 5))
    m = p["machine"]
    assert m["name"] == "Medieval Madness"
    assert m["headline"] == "Williams · 1997"
    assert m["summary"] == "Solid state · Dot matrix · 4 players"
    assert m["release_label"] == "June 25, 1997"
    assert m["era_label"] == "Dot matrix era"
    assert p["images"]["backglass"]["orientation"] == "landscape"
    assert p["images"]["playfield"]["orientation"] == "portrait"
    assert p["qr"]["url"] == "https://pinball-showcase.trmnlplugins.com/m/GAAAA-M0001"
    assert p["links"]["opdb"] == "https://opdb.org/search?q=GAAAA-M0001"
    assert p["featured"]["date_label"] == "Monday, October 5"
    assert p["error"] is None
    assert {"label": "Released", "value": "29 years ago"} in p["facts"]


def test_credits_one_row_per_role(dataset: Dataset) -> None:
    # Dan Forden is credited for music and sound: he appears on both rows.
    credits = render(dataset, "GAAAA", datetime(2026, 10, 5))["credits"]
    assert credits == [
        {"role": "Design", "names": "Brian Eddy"},
        {"role": "Art", "names": "John Youssi"},
        {"role": "Music", "names": "Dan Forden"},
        {"role": "Sound", "names": "Dan Forden"},
    ]


def test_updated_label_in_viewer_time_zone() -> None:
    from zoneinfo import ZoneInfo

    from pinball_showcase.presenter import updated_label

    ny = datetime(2026, 10, 5, 23, 42, tzinfo=ZoneInfo("America/New_York"))
    assert updated_label(ny) == "Oct 5, 2026 11:42 PM EDT"
    la = datetime(2026, 12, 1, 9, 5, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert updated_label(la) == "Dec 1, 2026 9:05 AM PST"
    # Zones without an abbreviation fall back to the UTC offset.
    assert updated_label(datetime(2026, 10, 5, 12, 0, tzinfo=ZoneInfo("Asia/Dubai"))).endswith(
        "12:00 PM GMT+4"
    )
    assert updated_label(datetime(2026, 10, 5, 0, 0, tzinfo=ZoneInfo("UTC"))).endswith("UTC")


def test_anniversary(dataset: Dataset) -> None:
    p = render(dataset, "GAAAA", datetime(2026, 6, 25))
    assert p["machine"]["anniversary"] is True
    assert p["fun_fact"].startswith("Happy birthday!")
    assert render(dataset, "GAAAA", datetime(2026, 6, 26))["machine"]["anniversary"] is False


def test_year_only_dates(dataset: Dataset) -> None:
    p = render(dataset, "GCCCC", datetime(2026, 1, 1))
    assert p["machine"]["release_label"] == "1954"
    assert p["machine"]["anniversary"] is False
    assert p["machine"]["type_label"] == "Electro-mechanical"
    assert p["machine"]["display_label"] == "Score reels"


def test_edition_tags_and_same_year(dataset: Dataset) -> None:
    p = render(dataset, "GBBBB", datetime(2026, 10, 5))
    assert [(e["label"], e["shown"]) for e in p["editions"]] == [
        ("Premium / Limited Edition", False),
        ("Pro", True),
    ]
    assert p["same_year_count"] == 0


def test_editions_list_every_version_and_mark_the_shown_one(dataset: Dataset) -> None:
    payload = render(dataset, "GAAAA", datetime(2026, 10, 5))
    assert payload["editions"] == [
        {"label": "Standard Edition", "short": "Standard", "id": "GAAAA-M0001", "shown": True},
        {
            "label": "Remake Limited Edition",
            "short": "Remake LE",
            "id": "GAAAA-M0002",
            "shown": False,
        },
    ]
    # Alias-only versions are listed too.
    labels = [e["label"] for e in render(dataset, "GDDDD", datetime(2026, 10, 5))["editions"]]
    assert labels == ["Standard Edition", "Special"]
    # Edition names are no longer mixed into the feature tags.
    assert "Remake LE" not in payload["machine"]["tags"]


def _pirates() -> Dataset:
    """Jersey Jack's Pirates in OPDB: a standard model with a backglass, a CE with no
    photos and an LE alias with only a playfield photo."""
    from pinball_showcase.dataset import build_dataset
    from tests.conftest import group, image, machine

    le = machine(
        "GPPPP-M0001-A0001", "Pirates (LE)", year=2018, images=[image("playfield", "le-pf")]
    )
    le.update(entryType="alias", opdbMachine="GPPPP-M0001")
    return build_dataset(
        {
            "entries": [
                group("GPPPP", "Pirates"),
                machine("GPPPP-M0001", "Pirates", year=2018, images=[image("backglass", "std-bg")]),
                machine("GPPPP-M0002", "Pirates (CE)", year=2018, images=[]),
                le,
            ]
        }
    )


def _show(ds: Dataset, opdb_id: str) -> dict:
    return build_showcase(
        ds,
        ds.lookup(opdb_id),
        local_now=datetime(2026, 10, 6),
        rotation=Rotation.DAILY,
        filters=Filters(),
        pool_size=1,
        period="2026-10-06",
        site_url="https://pinball-showcase.trmnlplugins.com",
        edition=ds.lookup_edition(opdb_id),
    )


def test_edition_without_photos_borrows_and_says_so() -> None:
    p = _show(_pirates(), "GPPPP-M0002")
    assert p["machine"]["edition_label"] == "Collector's Edition"
    assert p["machine"]["edition_short"] == "CE"
    art = p["images"]["any"]
    assert art["url"] == "https://img.opdb.org/std-bg-large.jpg"
    assert art["borrowed"] is True and art["edition"] == "Standard Edition"


def test_auto_art_prefers_the_editions_own_photos() -> None:
    p = _show(_pirates(), "GPPPP-M0001-A0001")
    assert p["machine"]["edition_label"] == "Limited Edition"
    # Its own playfield beats the standard model's backglass...
    assert "le-pf" in p["images"]["any"]["url"]
    assert p["images"]["any"]["borrowed"] is False
    assert "le-pf" in p["images"]["tall"]["url"]
    # ...but an explicit backglass request still borrows, labelled.
    assert p["images"]["backglass"]["borrowed"] is True
    assert p["images"]["backglass"]["edition"] == "Standard Edition"


def test_single_edition_titles_have_no_label(dataset: Dataset) -> None:
    p = render(dataset, "GCCCC", datetime(2026, 10, 6))
    assert p["machine"]["edition_label"] is None
    assert p["images"]["any"] is None or p["images"]["any"]["borrowed"] is False


def test_default_edition_is_labelled_when_there_are_others(dataset: Dataset) -> None:
    p = render(dataset, "GAAAA", datetime(2026, 10, 6))
    assert p["machine"]["edition_label"] == "Standard Edition"
    assert p["images"]["backglass"]["borrowed"] is False


def _addams() -> Dataset:
    """A standard model, a Gold edition, a Special Collectors Edition filed as an alias of
    the Gold (only a playfield photo and only a software credit) and another maker's remake
    with no credits."""
    from pinball_showcase.dataset import build_dataset
    from tests.conftest import group, image, machine

    sce = machine(
        "GTTTT-M0002-A0001",
        "The Addams Family (SCE)",
        year=2021,
        images=[image("playfield", "sce-pf")],
        people=[("Sce Coder", "software")],
    )
    sce.update(entryType="alias", opdbMachine="GTTTT-M0002", ipdbId=None)
    return build_dataset(
        {
            "entries": [
                group("GTTTT", "The Addams Family"),
                machine(
                    "GTTTT-M0001",
                    "The Addams Family",
                    year=1992,
                    images=[image("backglass", "std-bg")],
                    people=[("Std Designer", "design"), ("Std Artist", "art")],
                ),
                machine(
                    "GTTTT-M0002",
                    "The Addams Family (Gold)",
                    year=1994,
                    images=[image("backglass", "gold-bg")],
                    people=[("Gold Designer", "design"), ("Gold Artist", "art")],
                ),
                sce,
                machine(
                    "GTTTT-M0003",
                    "The Addams Family (Remake)",
                    year=2023,
                    maker="Chicago Gaming",
                    images=[image("cabinet", "remake-cab")],
                ),
            ]
        }
    )


def test_edition_fills_missing_roles_from_its_base_machine() -> None:
    p = _show(_addams(), "GTTTT-M0002-A0001")
    credits = {c["role"]: c["names"] for c in p["credits"]}
    # Its own software credit stays; design and art come from the Gold, not the standard.
    assert credits == {"Design": "Gold Designer", "Art": "Gold Artist", "Code": "Sce Coder"}
    assert p["machine"]["ipdb_id"] == 1


def test_edition_borrows_photos_from_its_base_machine_first() -> None:
    p = _show(_addams(), "GTTTT-M0002-A0001")
    assert "gold-bg" in p["images"]["backglass"]["url"]
    assert "sce-pf" in p["images"]["any"]["url"]


def test_remake_by_another_maker_does_not_inherit_credits() -> None:
    p = _show(_addams(), "GTTTT-M0003")
    assert p["credits"] == []
    # Photos still come from any edition, labelled as borrowed.
    assert p["images"]["backglass"]["borrowed"] is True
