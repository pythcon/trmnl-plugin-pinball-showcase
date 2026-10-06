"""Download, cache and refresh the OPDB export.

The export is fetched once a day (shortly after the upstream rebuild), written atomically
to ``data_dir`` and parsed into memory. Restarts reuse the cached file, conditional
requests (ETag / Last-Modified) avoid re-downloading an unchanged export, and a failed
refresh keeps serving the previous dataset.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .config import Settings
from .dataset import Dataset, build_dataset

log = logging.getLogger(__name__)

EXPORT_FILE = "opdb-v2.json"
META_FILE = "opdb-v2.meta.json"


class DatasetStore:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.dataset: Dataset | None = None
        self.last_attempt: datetime | None = None
        self.last_error: str | None = None
        self._client = client
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    # -- paths ---------------------------------------------------------------------------

    @property
    def export_path(self) -> Path:
        return self.settings.data_dir / EXPORT_FILE

    @property
    def meta_path(self) -> Path:
        return self.settings.data_dir / META_FILE

    def _read_meta(self) -> dict[str, Any]:
        try:
            return json.loads(self.meta_path.read_text())
        except (OSError, ValueError):
            return {}

    # -- lifecycle -----------------------------------------------------------------------

    async def start(self) -> None:
        """Load the cached export, fetch if missing/stale, then schedule daily refreshes."""
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        await self._load_cached()
        if self.dataset is None or self._cache_is_stale():
            await self.refresh()
        self._task = asyncio.create_task(self._scheduler(), name="opdb-refresh")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def _cache_is_stale(self) -> bool:
        fetched = self._read_meta().get("fetched_at")
        if not fetched:
            return True
        age = datetime.now(UTC) - datetime.fromisoformat(fetched)
        return age > timedelta(hours=self.settings.max_age_hours)

    async def _load_cached(self) -> None:
        if not self.export_path.exists():
            return
        meta = self._read_meta()
        try:
            dataset = await asyncio.to_thread(self._parse_file, self.export_path, meta)
        except (OSError, ValueError) as exc:
            log.warning("Ignoring unreadable cached export: %s", exc)
            return
        self.dataset = dataset
        log.info("Loaded cached OPDB export: %d titles", len(dataset.titles))

    def _parse_file(self, path: Path, meta: dict[str, Any]) -> Dataset:
        raw = json.loads(path.read_bytes())
        dataset = build_dataset(raw, source_last_modified=meta.get("last_modified"))
        if fetched := meta.get("fetched_at"):
            dataset.fetched_at = datetime.fromisoformat(fetched)
        return dataset

    # -- refresh -------------------------------------------------------------------------

    async def refresh(self, *, force: bool = False) -> bool:
        """Download the export if it changed. Returns True when a new dataset was loaded."""
        async with self._lock:
            self.last_attempt = datetime.now(UTC)
            try:
                changed = await self._download(force=force)
            except Exception as exc:  # keep serving the previous dataset
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.error("OPDB export refresh failed: %s", self.last_error)
                return False
            self.last_error = None
            return changed

    async def _download(self, *, force: bool) -> bool:
        meta = self._read_meta()
        headers = {"User-Agent": f"trmnl-pinball-showcase/{__version__}"}
        if not force and self.dataset is not None:
            if etag := meta.get("etag"):
                headers["If-None-Match"] = etag
            if last_modified := meta.get("last_modified"):
                headers["If-Modified-Since"] = last_modified

        client = self._client or httpx.AsyncClient(
            timeout=self.settings.download_timeout_seconds, follow_redirects=True
        )
        try:
            response = await client.get(self.settings.opdb_export_url, headers=headers)
        finally:
            if self._client is None:
                await client.aclose()

        now = datetime.now(UTC)
        if response.status_code == 304:
            log.info("OPDB export unchanged (304)")
            self._write_meta({**meta, "fetched_at": now.isoformat()})
            if self.dataset:
                self.dataset.fetched_at = now
            return False
        response.raise_for_status()

        raw = response.json()
        dataset = await asyncio.to_thread(
            build_dataset, raw, source_last_modified=response.headers.get("last-modified")
        )
        if dataset.entry_count < self.settings.min_entries:
            raise ValueError(
                f"export has only {dataset.entry_count} entries (< {self.settings.min_entries})"
            )
        dataset.fetched_at = now

        self._atomic_write(self.export_path, response.content)
        self._write_meta(
            {
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
                "fetched_at": now.isoformat(),
                "entry_count": dataset.entry_count,
                "source": self.settings.opdb_export_url,
            }
        )
        self.dataset = dataset
        log.info(
            "Loaded fresh OPDB export: %d entries, %d titles",
            dataset.entry_count,
            len(dataset.titles),
        )
        return True

    def _write_meta(self, meta: dict[str, Any]) -> None:
        self._atomic_write(self.meta_path, json.dumps(meta, indent=2).encode())

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(content)
        os.replace(tmp, path)

    # -- scheduling ----------------------------------------------------------------------

    def next_refresh(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now(UTC)
        target = datetime.combine(now.date(), self.settings.refresh_time_utc, tzinfo=UTC)
        if target <= now:
            target += timedelta(days=1)
        return target

    async def _scheduler(self) -> None:
        retry = timedelta(minutes=self.settings.retry_minutes)
        while True:
            now = datetime.now(UTC)
            wake = self.next_refresh(now)
            if self.last_error and self.last_attempt and self.last_attempt + retry < wake:
                wake = max(now, self.last_attempt + retry)
            log.info("Next OPDB refresh at %s", wake.isoformat())
            await asyncio.sleep(max(1.0, (wake - now).total_seconds()))
            await self.refresh()
