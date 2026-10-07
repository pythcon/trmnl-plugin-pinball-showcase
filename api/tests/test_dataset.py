from pinball_showcase.dataset import Dataset


def test_titles_group_editions(dataset: Dataset) -> None:
    godzilla = dataset.by_group["GBBBB"]
    assert godzilla.name == "Godzilla"
    # The Pro has a backglass image, the Premium/LE does not.
    assert godzilla.representative.opdb_id == "GBBBB-M0002"
    assert set(godzilla.editions) == {"Pro", "Premium / Limited Edition"}


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
    assert sorted(labels) == ["Arcade", "Collector's Edition", "Wizard"]
    # Default: the Pro-equivalent edition with photos.
    assert title.representative.opdb_id == "GHHHH-M0001-A0001"
    # An alias id pins that exact edition.
    ce = ds.lookup_edition("GHHHH-M0001-A0003")
    assert ce is not None and ce.name == "Harry Potter (CE)"
    assert ds.lookup("GHHHH-M0001-A0003") is title


def test_edition_labels_are_meaningful_and_unique() -> None:
    from pinball_showcase.dataset import build_dataset
    from tests.conftest import group, machine

    ds = build_dataset(
        {
            "entries": [
                group("GSSSS", "Super Star / Olympics"),
                machine("GSSSS-M0001", "Super Star", year=1975),
                machine("GSSSS-M0002", "Olympics", year=1975),
                group("GFFFF", "Fire!"),
                machine("GFFFF-M0001", "Fire!", year=1987),
                machine("GFFFF-M0002", "Fire! Champagne Edition", year=1987),
                group("GRRRR", "Roller Coaster"),
                machine("GRRRR-M0001", "Roller Coaster", year=1971, maker="Gottlieb"),
                machine("GRRRR-M0002", "Roller Coaster", year=1972, maker="Maresa"),
            ]
        }
    )

    def labels(group_id: str) -> list[str]:
        return sorted(ds.by_group[group_id].edition_labels().values())

    assert labels("GSSSS") == ["Olympics", "Super Star"]
    assert labels("GFFFF") == ["Champagne Edition", "Standard Edition"]
    assert labels("GRRRR") == ["Standard Edition (Gottlieb)", "Standard Edition (Maresa)"]


def test_edition_names_are_expanded() -> None:
    from pinball_showcase.editions import expand, is_edition_suffix, shorten

    assert expand("CE") == "Collector's Edition"
    assert expand("SE") == "Special Edition"
    assert expand("PE") == "Platinum Edition"
    assert expand("Premium/LE") == "Premium / Limited Edition"
    assert expand("Super LE") == "Super Limited Edition"
    assert expand("Back In Black LE") == "Back In Black Limited Edition"
    assert expand("4P") == "4 Player" and expand("AAB") == "Add-A-Ball"
    assert expand("Blood Sucker Edition") == "Blood Sucker Edition"  # already words
    assert expand("Pro") == "Pro" and expand("Arcade") == "Arcade"
    assert shorten("Blood Sucker Edition") == "Blood Sucker" and shorten("CE") == "CE"
    assert is_edition_suffix("SE") and is_edition_suffix("Home Edition")
    assert not is_edition_suffix("Inder")


def test_editions_baked_into_game_names_are_removed_and_badged() -> None:
    """OPDB names a few games with an edition: "The Texas Chainsaw Massacre (SE)",
    "Star Wars (Home Edition)". The name drops it; the badge carries it."""
    from pinball_showcase.dataset import build_dataset
    from tests.conftest import group, machine

    ds = build_dataset(
        {
            "entries": [
                group("GTTTT", "The Texas Chainsaw Massacre (SE)"),
                machine("GTTTT-M0001", "The Texas Chainsaw Massacre (SE)", year=2024),
                machine("GTTTT-M0002", "The Texas Chainsaw Massacre (CE)", year=2024),
                group("GHOME", "Star Wars (Home Edition)"),
                machine("GHOME-M0001", "Star Wars (Home Edition)", year=2019),
                group("GINDR", "Centaur (Inder)"),
                machine("GINDR-M0001", "Centaur", year=1982),
                group("GSOLO", "Gold Star"),
                machine("GSOLO-M0001", "Gold Star", year=1954),
            ]
        }
    )
    tcm = ds.by_group["GTTTT"]
    assert tcm.name == "The Texas Chainsaw Massacre"
    assert tcm.badge(tcm.machines[0]) == ("Special Edition", "SE")
    home = ds.by_group["GHOME"]
    assert home.name == "Star Wars"
    # A single edition that is a named one still gets its badge.
    assert home.badge(home.machines[0]) == ("Home Edition", "Home")
    # A maker in parentheses isn't an edition: left alone.
    centaur = ds.by_group["GINDR"]
    assert centaur.name == "Centaur (Inder)"
    assert centaur.badge(centaur.machines[0]) is None  # its plain model, no badge
    # A plain single model gets no badge.
    solo = ds.by_group["GSOLO"]
    assert solo.badge(solo.machines[0]) is None
