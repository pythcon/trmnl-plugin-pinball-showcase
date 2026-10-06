"""HTTP API. TRMNL polls ``GET /api/v1/showcase`` and renders the JSON as merge variables."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings, get_settings
from .dataset import Dataset
from .options import filter_options
from .params import ShowcaseParams, blank_to_none, parse_rotation, to_filters
from .presenter import build_error, build_showcase
from .selection import Filters, PickMemo, Rotation, choose, period_key
from .store import DatasetStore

log = logging.getLogger("pinball_showcase")


def create_app(settings: Settings | None = None, store: DatasetStore | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    store = store or DatasetStore(settings)
    memo = PickMemo(None)  # replaced with a disk-backed memo at startup

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal memo
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        memo = PickMemo(settings.data_dir / "picks.json")
        await store.start()
        yield
        await store.stop()

    app = FastAPI(
        title="TRMNL Pinball Showcase API",
        version=__version__,
        description="Featured pinball machine for TRMNL e-ink displays, built from the OPDB daily export.",
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.settings = settings

    def require_dataset() -> Dataset:
        if store.dataset is None:
            raise HTTPException(status_code=503, detail="OPDB dataset is not loaded yet")
        return store.dataset

    def cached(payload: dict[str, Any], response: Response) -> dict[str, Any]:
        response.headers["Cache-Control"] = f"public, max-age={settings.cache_max_age_seconds}"
        return payload

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "trmnl-pinball-showcase", "version": __version__, "docs": "/docs"}

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        """Liveness: the process is up."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz() -> JSONResponse:
        """Readiness: a dataset is loaded and can be served."""
        info = _dataset_info(store)
        return JSONResponse(info, status_code=200 if store.dataset else 503)

    @app.get("/api/v1/dataset", tags=["showcase"])
    def dataset_info() -> dict[str, Any]:
        """Metadata about the cached OPDB export."""
        return _dataset_info(store)

    @app.get("/api/v1/showcase", tags=["showcase"])
    def showcase(response: Response, params: Annotated[ShowcaseParams, Query()]) -> dict[str, Any]:
        """The featured machine for the current rotation period, as TRMNL merge variables.

        Multi-value filters accept repeated parameters or comma-separated lists. Values in
        one filter are OR'd; different filters are AND'd.
        """
        dataset = require_dataset()
        local_now = _local_now(params.tz or settings.default_timezone, params.date)
        rotation = parse_rotation(params.rotation)
        filters = to_filters(params)
        period = period_key(local_now, rotation)

        if pinned := blank_to_none(params.machine):
            title = dataset.lookup(pinned)
            pool_size = 1
            if title is None:
                return cached(
                    build_error("Machine not found", f"No OPDB machine with id {pinned}."), response
                )
        else:
            title, pool_size = choose(dataset, filters, local_now, rotation, memo)
            if title is None:
                return cached(
                    build_error(
                        "No matches", "No machines match these filters. Try widening them."
                    ),
                    response,
                )

        payload = build_showcase(
            dataset,
            title,
            local_now=local_now,
            rotation=rotation,
            filters=filters,
            pool_size=pool_size,
            period=period,
        )
        return cached(payload, response)

    @app.get("/api/v1/options", tags=["showcase"])
    def options(response: Response) -> dict[str, Any]:
        """Every accepted filter value, with title counts from the current dataset."""
        return cached(filter_options(require_dataset()), response)

    @app.get("/api/v1/machines/{opdb_id}", tags=["showcase"])
    def machine_detail(
        opdb_id: str,
        response: Response,
        tz: Annotated[str | None, Query(max_length=64)] = None,
    ) -> dict[str, Any]:
        """Showcase payload for one machine (any OPDB machine, group or alias id)."""
        dataset = require_dataset()
        title = dataset.lookup(opdb_id)
        if title is None:
            raise HTTPException(status_code=404, detail=f"Unknown OPDB id {opdb_id}")
        local_now = _local_now(tz or settings.default_timezone, None)
        payload = build_showcase(
            dataset,
            title,
            local_now=local_now,
            rotation=Rotation.DAILY,
            filters=Filters(),
            pool_size=1,
            period=local_now.date().isoformat(),
        )
        return cached(payload, response)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error: %s", exc)
        return JSONResponse(
            build_error("Server error", "Something went wrong. Try again shortly."), status_code=500
        )

    return app


def _dataset_info(store: DatasetStore) -> dict[str, Any]:
    ds = store.dataset
    return {
        "loaded": ds is not None,
        "entries": ds.entry_count if ds else 0,
        "titles": len(ds.titles) if ds else 0,
        "showcase_titles": len(ds.showcase_titles) if ds else 0,
        "source_last_modified": ds.source_last_modified if ds else None,
        "fetched_at": ds.fetched_at.isoformat() if ds else None,
        "next_refresh": store.next_refresh().isoformat(),
        "last_error": store.last_error,
    }


def _local_now(tz_name: str, date_override: str | None) -> datetime:
    try:
        tz = ZoneInfo(tz_name.strip())
    except (ZoneInfoNotFoundError, ValueError):
        tz = UTC
    now = datetime.now(tz)
    if date_override := blank_to_none(date_override):
        try:
            d = datetime.fromisoformat(date_override)
        except ValueError:
            return now
        now = now.replace(year=d.year, month=d.month, day=d.day)
    return now


app = create_app()
