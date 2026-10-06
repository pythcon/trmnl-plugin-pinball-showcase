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
