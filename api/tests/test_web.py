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
    assert "Music &amp; Sound" in html
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
