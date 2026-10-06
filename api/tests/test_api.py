import pytest
from fastapi.testclient import TestClient

from pinball_showcase.dataset import build_dataset
from pinball_showcase.main import create_app
from pinball_showcase.store import DatasetStore


class StaticStore(DatasetStore):
    """A store preloaded with the sample dataset that never touches the network."""

    def __init__(self, settings, dataset):
        super().__init__(settings)
        self.dataset = dataset

    async def start(self) -> None:
        return None


@pytest.fixture
def client(settings, export):
    store = StaticStore(settings, build_dataset(export))
    with TestClient(create_app(settings, store)) as c:
        yield c


def test_health(client) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["showcase_titles"] == 4


def test_showcase(client) -> None:
    r = client.get("/api/v1/showcase", params={"tz": "America/New_York", "date": "2026-10-05"})
    assert r.status_code == 200
    assert "max-age" in r.headers["cache-control"]
    body = r.json()
    assert body["machine"]["name"]
    assert body["featured"]["date"] == "2026-10-05"
    assert body["featured"]["pool_size"] == 4


def test_showcase_is_stable_for_a_day(client) -> None:
    a = client.get("/api/v1/showcase", params={"date": "2026-10-05"}).json()
    b = client.get("/api/v1/showcase", params={"date": "2026-10-05"}).json()
    assert a["machine"]["id"] == b["machine"]["id"]


def test_blank_trmnl_params_use_defaults(client) -> None:
    params = dict.fromkeys(
        ["rotation", "era", "manufacturer", "min_year", "max_year", "machine", "tz"], ""
    )
    body = client.get("/api/v1/showcase", params=params).json()
    assert body["error"] is None
    assert body["featured"]["rotation"] == "daily"


def test_invalid_values_fall_back(client) -> None:
    body = client.get(
        "/api/v1/showcase", params={"era": "bogus", "tz": "Mars/Base", "min_year": "abc"}
    ).json()
    assert body["error"] is None


def test_filters(client) -> None:
    body = client.get("/api/v1/showcase", params={"era": "em"}).json()
    assert body["machine"]["name"] == "Gold Star"
    assert body["featured"]["filter_label"] == "Electro-mechanical"


def test_multi_value_params(client) -> None:
    body = client.get(
        "/api/v1/showcase",
        params=[("manufacturer", "williams, bally"), ("decade", "1990s"), ("era", "dmd")],
    ).json()
    assert body["machine"]["name"] in {"Medieval Madness", "Attack from Mars"}
    assert body["featured"]["pool_size"] == 2
    fav = client.get("/api/v1/showcase", params={"favorites": "GCCCC,GDDDD-M0001"}).json()
    assert fav["featured"]["pool_size"] == 2
    assert fav["featured"]["filter_label"] == "Favorites"


def test_options(client) -> None:
    body = client.get("/api/v1/options").json()
    assert body["total_titles"] == 4
    assert {"value": 1990, "label": "1990s", "titles": 2} in body["decade"]
    assert body["manufacturer"][0]["value"]


def test_no_matches_returns_error_payload(client) -> None:
    body = client.get("/api/v1/showcase", params={"manufacturer": "nobody"}).json()
    assert body["error"]["title"] == "No matches"


def test_pinned_machine(client) -> None:
    body = client.get("/api/v1/showcase", params={"machine": "GDDDD"}).json()
    assert body["machine"]["name"] == "Attack from Mars"
    missing = client.get("/api/v1/showcase", params={"machine": "GZZZZ"}).json()
    assert missing["error"]["title"] == "Machine not found"


def test_machine_detail(client) -> None:
    assert (
        client.get("/api/v1/machines/GAAAA-M0002").json()["machine"]["name"] == "Medieval Madness"
    )
    assert client.get("/api/v1/machines/nope").status_code == 404


def test_not_ready(settings) -> None:
    store = StaticStore(settings, None)
    with TestClient(create_app(settings, store)) as c:
        assert c.get("/readyz").status_code == 503
        assert c.get("/api/v1/showcase").status_code == 503


def test_showcase_reports_updated_time_in_viewer_zone(client) -> None:
    body = client.get("/api/v1/showcase", params={"tz": "America/New_York"}).json()
    assert body["featured"]["timezone"] in {"EDT", "EST"}
    assert body["featured"]["updated_label"].endswith(body["featured"]["timezone"])


def test_shuffle_avoids_the_previous_machine(client) -> None:
    first = client.get("/api/v1/showcase", params={"rotation": "shuffle"}).json()
    for _ in range(20):
        nxt = client.get(
            "/api/v1/showcase", params={"rotation": "shuffle", "avoid": first["machine"]["id"]}
        ).json()
        assert nxt["machine"]["group_id"] != first["machine"]["group_id"]


def test_refresh_rotation_accepts_interval(client) -> None:
    body = client.get("/api/v1/showcase", params={"rotation": "refresh", "interval": "15"}).json()
    assert body["featured"]["rotation"] == "refresh"
    assert body["featured"]["period"].startswith("15m-")
