"""The plugin's dropdowns (plugin/bin/sync-options) stay in step with /api/v1/options."""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest
import yaml

from pinball_showcase.options import filter_options
from pinball_showcase.selection import Rotation

from .test_api import client  # noqa: F401  (fixture)

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
SETTINGS = PLUGIN / "src" / "settings.yml"


def load_sync():
    path = PLUGIN / "bin" / "sync-options"
    loader = importlib.machinery.SourceFileLoader("sync_options", str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sync():
    return load_sync()


def fields(text: str) -> dict[str, dict]:
    return {f["keyname"]: f for f in yaml.safe_load(text)["custom_fields"]}


def values(field: dict) -> list[str]:
    return [next(iter(o.values())) for o in field["options"]]


def test_rotation_options_match_api() -> None:
    assert values(fields(SETTINGS.read_text())["rotation"]) == [r.value for r in Rotation]


def test_sync_rewrites_only_option_lists(sync, dataset, client) -> None:  # noqa: F811
    before = SETTINGS.read_text()
    options = filter_options(dataset)
    after = sync.sync(before, options)
    old, new = fields(before), fields(after)

    for keyname, source in sync.FIELDS.items():
        synced = values(new[keyname])
        assert synced == [str(o["value"]) for o in options[source] if o["titles"]]
    for keyname in old.keys() - sync.FIELDS.keys():
        assert new[keyname] == old[keyname]
    assert new["manufacturers"]["options"] == new["exclude_manufacturers"]["options"]
    assert new["features"]["options"] == new["exclude_features"]["options"]
    # Field text outside the option lists (descriptions, comments) is untouched.
    kept = [line for line in after.splitlines() if not line.startswith("  - ")]
    assert kept == [line for line in before.splitlines() if not line.startswith("  - ")]
    assert sync.sync(after, options) == after

    for maker in values(new["manufacturers"]):
        body = client.get("/api/v1/showcase", params={"manufacturer": maker}).json()
        assert not body.get("error"), maker


def test_sync_drops_options_without_titles(sync, dataset) -> None:
    options = filter_options(dataset)
    decades = values(fields(sync.sync(SETTINGS.read_text(), options))["decades"])
    assert decades == [str(d["value"]) for d in options["decade"]]
    assert "1930" not in decades


def test_sync_refuses_rotation_drift(sync, dataset) -> None:
    options = {**filter_options(dataset), "rotation": ["daily"]}
    with pytest.raises(SystemExit, match="rotation"):
        sync.sync(SETTINGS.read_text(), options)
