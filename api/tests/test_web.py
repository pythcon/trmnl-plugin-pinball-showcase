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
    assert '<h1>Medieval Madness <span class="edition-badge">Standard</span></h1>' in html
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
    # Gallery: carousel slides, thumbnails that target them, full-size links without JS.
    assert 'class="gallery-slide" id="photo-1"' in html and 'href="#photo-2"' in html
    assert 'class="gallery-thumbs"' in html and "/static/gallery.js" in html
    assert 'href="https://img.opdb.org/mm-bg-large.jpg" target="_blank"' in html
    assert "Shown</span>" in html  # current edition in the editions table
    assert "Remake" in html


def test_alias_editions_and_resources(settings, export) -> None:
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
    # Alias versions are listed as editions, not as alternate names.
    assert "Also released as" not in html
    assert '<a href="/m/GDDDD-M0001-A0001">Attack from Mars (Special)</a>' in html
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


def test_alias_editions_are_listed_and_linked(client) -> None:
    html = client.get("/m/GDDDD").text
    assert "Attack from Mars (Special)" in html
    assert '<a href="/m/GDDDD-M0001-A0001">Attack from Mars (Special)</a>' in html


def test_edition_page_names_the_edition_and_captions_borrowed_photos(client) -> None:
    # Godzilla Premium/LE has no photos of its own: the hero is the Pro's, captioned.
    html = client.get("/m/GBBBB-M0001").text
    assert '<span class="edition-badge">Premium/LE</span>' in html
    assert "Photo of the Pro edition. OPDB has no photos of the Premium/LE yet." in html
    assert "<title>Godzilla Premium/LE" in html


def test_own_photos_have_no_borrowed_caption(client) -> None:
    html = client.get("/m/GAAAA-M0001").text
    assert "hero-note" not in html


def test_header_has_search_on_every_page(client) -> None:
    for path in ("/", "/m/GAAAA-M0001"):
        html = client.get(path).text
        assert 'action="/search"' in html and 'role="combobox"' in html
        assert "/static/search.js" in html


def test_search_page_lists_results(client) -> None:
    r = client.get("/search", params={"q": "godzilla prem"})
    assert r.status_code == 200
    assert r.headers["x-robots-tag"] == "noindex"
    html = r.text
    assert "1 match for &ldquo;godzilla prem&rdquo;" in html
    assert '<a class="card" href="/m/GBBBB-M0001">' in html
    assert '<span class="edition-badge">Premium/LE</span>' in html
    # The box keeps what was typed.
    assert 'value="godzilla prem"' in html


def test_search_page_empty_and_no_match(client) -> None:
    assert "Search 5 machines" in client.get("/search").text
    assert "No machines match that." in client.get("/search", params={"q": "zzzz"}).text


def test_search_page_escapes_the_query(client) -> None:
    html = client.get("/search", params={"q": "<script>alert(1)</script>"}).text
    assert "<script>alert(1)</script>" not in html


def test_security_headers(client) -> None:
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "max-age=" in r.headers["strict-transport-security"]
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "https://img.opdb.org" in csp
    # The API docs keep working (their CDN script isn't blocked).
    assert "content-security-policy" not in client.get("/docs").headers
    assert client.get("/api/v1/showcase").headers["x-content-type-options"] == "nosniff"
