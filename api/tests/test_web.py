import pytest
from fastapi.testclient import TestClient

from pinball_showcase.config import Settings
from pinball_showcase.dataset import build_dataset
from pinball_showcase.main import create_app
from tests.test_api import StaticStore


@pytest.fixture
def client(settings, export):
    store = StaticStore(settings, build_dataset(export))
    with TestClient(create_app(settings, store)) as c:
        yield c


def test_home_page(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    html = r.text
    assert "Pinball of the Day" in html
    assert "Recently featured" in html
    assert "Open Pinball Database (OPDB)" in html  # credit
    assert "https://trmnlplugins.com" in html  # more plugins
    assert 'href="http://testserver/m/' in html


def test_machine_page(client) -> None:
    r = client.get("/m/GAAAA-M0001")
    assert r.status_code == 200
    html = r.text
    assert "<h1>Medieval Madness</h1>" in html
    assert "Brian Eddy" in html
    assert "<dt>Music</dt>" in html and "<dt>Sound</dt>" in html
    assert "Editions" in html  # original + remake
    assert "https://opdb.org/search?q=GAAAA-M0001" in html
    assert "https://www.ipdb.org/machine.cgi?id=1" in html
    assert "mm-pf-large.jpg" in html  # playfield in the gallery


def test_machine_page_accepts_group_ids(client) -> None:
    assert client.get("/m/GDDDD").status_code == 200


def test_unknown_machine_is_404_page(client) -> None:
    r = client.get("/m/GZZZZ")
    assert r.status_code == 404
    assert "couldn't find that machine" in r.text


def test_static_assets(client) -> None:
    assert client.get("/static/site.css").status_code == 200
    assert client.get("/static/favicon.svg").status_code == 200


def test_qr_points_at_machine_page(client) -> None:
    body = client.get("/api/v1/showcase", params={"machine": "GDDDD"}).json()
    assert body["qr"]["url"] == "http://testserver/m/GDDDD-M0001"
    page = client.get(body["qr"]["url"].replace("http://testserver", ""))
    assert page.status_code == 200


def test_public_url_setting(tmp_path, export) -> None:
    settings = Settings(data_dir=tmp_path, public_url="https://pinball-showcase.trmnlplugins.com/")
    store = StaticStore(settings, build_dataset(export))
    with TestClient(create_app(settings, store)) as c:
        body = c.get("/api/v1/showcase", params={"machine": "GDDDD"}).json()
        assert body["qr"]["url"] == "https://pinball-showcase.trmnlplugins.com/m/GDDDD-M0001"


def test_site_is_503_until_data_loads(settings) -> None:
    with TestClient(create_app(settings, StaticStore(settings, None))) as c:
        assert c.get("/").status_code == 503


def test_machine_profile_shows_everything(client, export) -> None:
    # Give Medieval Madness the optional OPDB links and a captioned closeup.
    html = client.get("/m/GAAAA-M0001").text
    assert "At a glance" in html
    assert "Known as <strong>MM</strong>" in html
    assert "has a dot matrix display and plays up to 4 players" in html
    assert 'id="photo-1"' in html and 'href="#photo-2"' in html  # lightbox navigation
    assert "photos</p>" in html  # photo strip
    assert "Shown</span>" in html  # current edition in the editions table
    assert "Remake" in html


def test_aliases_and_resources(settings, export) -> None:
    from pinball_showcase.main import create_app

    entries = export["entries"]
    afm = next(e for e in entries if e.get("opdbId") == "GDDDD-M0001")
    afm["pinballPrimerUrl"] = "https://pinballprimer.github.io/afm.html"
    afm["competitionNotesUrl"] = (
        "https://raw.githubusercontent.com/someone/notes/refs/heads/main/machines/AFM.md"
    )
    store = StaticStore(settings, build_dataset(export))
    with TestClient(create_app(settings, store)) as c:
        html = c.get("/m/GDDDD").text
    assert "Also released as Attack from Mars (Special)" in html
    assert "https://pinballprimer.github.io/afm.html" in html
    # Raw GitHub links are turned into readable GitHub pages.
    assert "https://github.com/someone/notes/blob/main/machines/AFM.md" in html


def test_edition_url_shows_that_edition(client) -> None:
    html = client.get("/m/GBBBB-M0001").text
    # The Premium/LE row is the one marked as shown, and the Pro row links to its page.
    assert 'Godzilla (Premium/LE) <span class="badge">Shown</span>' in html
    assert '<a href="/m/GBBBB-M0002">Godzilla (Pro)</a>' in html
    # Edition flags live in the Editions table, not the Features panel.
    assert '<p class="feature-group">Editions</p>' not in html


def test_alias_only_versions_are_listed(client) -> None:
    html = client.get("/m/GDDDD").text
    assert "Attack from Mars (Special)" in html
    assert "(name only in OPDB)" in html
