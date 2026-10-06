import json

import httpx
import pytest
import respx

from pinball_showcase.store import DatasetStore


@pytest.fixture
def mock_export(settings, export):
    with respx.mock(assert_all_called=False) as router:
        route = router.get(settings.opdb_export_url).mock(
            return_value=httpx.Response(
                200,
                json=export,
                headers={"etag": '"v1"', "last-modified": "Mon, 05 Oct 2026 06:30:14 GMT"},
            )
        )
        yield route


async def test_download_writes_cache_and_meta(settings, mock_export) -> None:
    store = DatasetStore(settings)
    assert await store.refresh() is True
    assert store.dataset is not None
    assert store.export_path.exists()
    meta = json.loads(store.meta_path.read_text())
    assert meta["etag"] == '"v1"'
    assert store.dataset.source_last_modified == "Mon, 05 Oct 2026 06:30:14 GMT"


async def test_not_modified_keeps_dataset(settings, mock_export) -> None:
    store = DatasetStore(settings)
    await store.refresh()
    first = store.dataset
    mock_export.mock(return_value=httpx.Response(304))
    assert await store.refresh() is False
    assert store.dataset is first
    assert mock_export.calls.last.request.headers["if-none-match"] == '"v1"'


async def test_failure_keeps_previous_dataset(settings, mock_export) -> None:
    store = DatasetStore(settings)
    await store.refresh()
    first = store.dataset
    mock_export.mock(return_value=httpx.Response(500))
    assert await store.refresh() is False
    assert store.dataset is first
    assert store.last_error and "500" in store.last_error


async def test_tiny_export_is_rejected(settings, mock_export) -> None:
    settings.min_entries = 10_000
    store = DatasetStore(settings)
    assert await store.refresh() is False
    assert store.dataset is None
    assert not store.export_path.exists()


async def test_start_uses_fresh_cache_without_network(settings, mock_export) -> None:
    await DatasetStore(settings).refresh()
    calls = mock_export.call_count
    store = DatasetStore(settings)
    await store.start()
    try:
        assert store.dataset is not None
        assert mock_export.call_count == calls
    finally:
        await store.stop()


def test_next_refresh_is_midnight_new_york_across_dst(settings) -> None:
    from datetime import UTC, datetime

    store = DatasetStore(settings)  # defaults: 00:00 America/New_York
    # October (EDT, UTC-4): midnight NY is 04:00 UTC.
    assert store.next_refresh(datetime(2026, 10, 6, 1, 0, tzinfo=UTC)) == datetime(
        2026, 10, 6, 4, 0, tzinfo=UTC
    )
    assert store.next_refresh(datetime(2026, 10, 6, 5, 0, tzinfo=UTC)) == datetime(
        2026, 10, 7, 4, 0, tzinfo=UTC
    )
    # December (EST, UTC-5): midnight NY is 05:00 UTC.
    assert store.next_refresh(datetime(2026, 12, 1, 12, 0, tzinfo=UTC)) == datetime(
        2026, 12, 2, 5, 0, tzinfo=UTC
    )


def test_legacy_utc_setting_still_works(tmp_path, monkeypatch) -> None:
    from datetime import UTC, datetime

    from pinball_showcase.config import Settings

    monkeypatch.setenv("PINBALL_REFRESH_TIME_UTC", "07:00")
    s = Settings(data_dir=tmp_path, refresh_timezone="UTC")
    assert DatasetStore(s).next_refresh(datetime(2026, 10, 6, 6, 0, tzinfo=UTC)) == datetime(
        2026, 10, 6, 7, 0, tzinfo=UTC
    )
