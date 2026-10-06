from pinball_showcase.dataset import Dataset


def test_titles_group_editions(dataset: Dataset) -> None:
    godzilla = dataset.by_group["GBBBB"]
    assert godzilla.name == "Godzilla"
    # The Pro has a backglass image, the Premium/LE does not.
    assert godzilla.representative.opdb_id == "GBBBB-M0002"
    assert set(godzilla.editions) == {"Pro", "Premium/LE"}


def test_representative_prefers_original_over_remake(dataset: Dataset) -> None:
    mm = dataset.by_group["GAAAA"]
    assert mm.representative.opdb_id == "GAAAA-M0001"
    assert mm.short_name == "MM"


def test_showcase_titles_need_physical_machine_and_images(dataset: Dataset) -> None:
    ids = {t.group_id for t in dataset.showcase_titles}
    assert ids == {"GAAAA", "GBBBB", "GCCCC", "GDDDD"}


def test_lookup_accepts_machine_group_and_alias_ids(dataset: Dataset) -> None:
    assert dataset.lookup("GAAAA-M0002").group_id == "GAAAA"
    assert dataset.lookup("GDDDD").group_id == "GDDDD"
    assert dataset.lookup("GDDDD-M0001-A0001").group_id == "GDDDD"
    assert dataset.lookup("nope") is None


def test_manufacturer_position_is_chronological(dataset: Dataset) -> None:
    mm = dataset.by_group["GAAAA"]
    # Williams titles (physical): No Images (1980), Medieval Madness (1997).
    assert dataset.manufacturer_position(mm) == (2, 2)


def test_umbrella_machine_with_alias_editions() -> None:
    """Harry Potter: a bare machine without photos whose real editions are aliases."""
    from pinball_showcase.dataset import build_dataset
    from tests.conftest import group, image, machine

    def alias(opdb_id: str, name: str, features: list, images: list) -> dict:
        entry = machine(opdb_id, name, year=2025, maker="Jersey Jack Pinball", images=images)
        entry.update(
            entryType="alias",
            opdbMachine="GHHHH-M0001",
            features=[{"featureId": 0, "name": n, "group": "edition"} for n in features],
        )
        return entry

    ds = build_dataset(
        {
            "entries": [
                group("GHHHH", "Harry Potter"),
                machine("GHHHH-M0001", "Harry Potter", year=2025, images=[]),
                alias(
                    "GHHHH-M0001-A0001",
                    "Harry Potter (Arcade)",
                    ["Pro edition"],
                    [image("backglass", "hp-a")],
                ),
                alias(
                    "GHHHH-M0001-A0002",
                    "Harry Potter (Wizard)",
                    ["Premium edition"],
                    [image("backglass", "hp-w")],
                ),
                alias(
                    "GHHHH-M0001-A0003",
                    "Harry Potter (CE)",
                    ["Premium edition"],
                    [image("backglass", "hp-c")],
                ),
            ]
        }
    )
    title = ds.by_group["GHHHH"]
    # The bare umbrella entry is not an edition, and nothing is called "Standard".
    labels = [e["label"] for e in title.edition_list(title.representative)]
    assert sorted(labels) == ["Arcade", "CE", "Wizard"]
    # Default: the Pro-equivalent edition with photos.
    assert title.representative.opdb_id == "GHHHH-M0001-A0001"
    # An alias id pins that exact edition.
    ce = ds.lookup_edition("GHHHH-M0001-A0003")
    assert ce is not None and ce.name == "Harry Potter (CE)"
    assert ds.lookup("GHHHH-M0001-A0003") is title
