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
    assert p["qr"]["url"].endswith("GAAAA-M0001")
    assert p["featured"]["date_label"] == "Monday, October 5"
    assert p["error"] is None
    assert {"label": "Released", "value": "29 years ago"} in p["facts"]


def test_credits_merge_shared_roles(dataset: Dataset) -> None:
    credits = render(dataset, "GAAAA", datetime(2026, 10, 5))["credits"]
    assert credits == [
        {"role": "Design", "names": "Brian Eddy"},
        {"role": "Art", "names": "John Youssi"},
        {"role": "Music & Sound", "names": "Dan Forden"},
    ]


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
    assert set(p["machine"]["tags"]) == {"Pro", "Premium/LE"}
    assert p["same_year_count"] == 0
