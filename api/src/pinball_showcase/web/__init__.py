"""Public website: today's machine, recent picks, and a page for every machine.

The QR code on the TRMNL screen links to ``/m/{opdb_id}``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..config import Settings
from ..dataset import Dataset, Title
from ..presenter import (
    DISPLAY_LABELS,
    TYPE_LABELS,
    build_showcase,
    machine_page_url,
    opdb_url,
)
from ..selection import (
    Filters,
    PickMemo,
    Rotation,
    candidate_pool,
    choose,
    period_index,
    pick,
)

HERE = Path(__file__).parent
STATIC_DIR = HERE / "static"
MORE_PLUGINS_URL = "https://trmnlplugins.com"
GITHUB_URL = "https://github.com/pythcon/trmnl-plugin-pinball-showcase"
RECENT_DAYS = 6
IMAGE_LABELS = {
    "backglass": "Backglass",
    "playfield": "Playfield",
    "cabinet": "Cabinet",
    "closeup": "Close-up",
    "other": "Photo",
}

templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals.update(
    more_plugins_url=MORE_PLUGINS_URL,
    github_url=GITHUB_URL,
    version=__version__,
    current_year=date.today().year,
)


def mount_static(app: Any) -> None:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def build_router(
    settings: Settings,
    get_dataset: Callable[[], Dataset | None],
    get_memo: Callable[[], PickMemo],
    base_url: Callable[[Request], str],
    local_now: Callable[[str | None], datetime],
) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    def dataset_or_503() -> Dataset:
        dataset = get_dataset()
        if dataset is None:
            raise HTTPException(
                status_code=503, detail="The pinball data is loading. Try again shortly."
            )
        return dataset

    def render(
        request: Request, name: str, context: dict[str, Any], status: int = 200
    ) -> HTMLResponse:
        context = {"site_url": base_url(request), **context}
        response = templates.TemplateResponse(request, name, context, status_code=status)
        response.headers["Cache-Control"] = f"public, max-age={settings.cache_max_age_seconds}"
        return response

    @router.get("/", response_class=HTMLResponse)
    def home(request: Request, tz: str | None = None) -> HTMLResponse:
        dataset = dataset_or_503()
        now = local_now(tz)
        title, _ = choose(dataset, Filters(), now, Rotation.DAILY, get_memo())
        if title is None:
            raise HTTPException(status_code=503, detail="No machines available yet.")
        site = base_url(request)
        today = machine_view(dataset, title, now, site)

        pool = candidate_pool(dataset, Filters())
        recent = []
        for days_back in range(1, RECENT_DAYS + 1):
            then = now - timedelta(days=days_back)
            past = pick(pool, period_index(then, Rotation.DAILY), Filters())
            if past is not None:
                recent.append(card_view(past, site, then.date()))

        return render(
            request,
            "home.html",
            {
                "today": today,
                "recent": recent,
                "date_label": f"{now:%A, %B} {now.day}",
                "catalog_size": len(dataset.showcase_titles),
                "page_title": f"Pinball of the Day: {today['name']}",
                "page_description": (
                    f"Today's featured pinball machine is {today['name']} "
                    f"({today['headline']}). A new machine every day on your TRMNL."
                ),
                "og_image": today["hero"]["url"] if today["hero"] else None,
            },
        )

    @router.get("/m/{opdb_id}", response_class=HTMLResponse)
    def machine_page(request: Request, opdb_id: str, tz: str | None = None) -> HTMLResponse:
        dataset = dataset_or_503()
        title = dataset.lookup(opdb_id)
        if title is None:
            return render(
                request,
                "not_found.html",
                {"page_title": "Machine not found", "opdb_id": opdb_id},
                status=404,
            )
        view = machine_view(dataset, title, local_now(tz), base_url(request))
        return render(
            request,
            "machine.html",
            {
                "m": view,
                "page_title": f"{view['name']} ({view['headline']})",
                "page_description": view["description"],
                "og_image": view["hero"]["url"] if view["hero"] else None,
            },
        )

    return router


# -- view models ---------------------------------------------------------------------------


def card_view(title: Title, site_url: str, shown_on: date | None = None) -> dict[str, Any]:
    rep = title.representative
    image = rep.image("backglass") or (rep.images[0] if rep.images else None)
    return {
        "name": title.name,
        "maker": rep.manufacturer,
        "year": title.year,
        "url": machine_page_url(site_url, rep),
        "image": image.url("medium") if image else None,
        "shown_on": f"{shown_on:%a, %b} {shown_on.day}" if shown_on else None,
    }


def machine_view(dataset: Dataset, title: Title, now: datetime, site_url: str) -> dict[str, Any]:
    """Everything the machine page shows, built on the same payload the plugin renders."""
    base = build_showcase(
        dataset,
        title,
        local_now=now,
        rotation=Rotation.DAILY,
        filters=Filters(),
        pool_size=1,
        period=now.date().isoformat(),
        site_url=site_url,
    )
    m = base["machine"]
    rep = title.representative

    gallery: list[dict[str, Any]] = []
    seen: set[str] = set()
    for machine in (rep, *title.machines):
        for image in sorted(machine.images, key=lambda i: (not i.primary, i.type)):
            large = image.url("large")
            if not large or large in seen:
                continue
            seen.add(large)
            label = IMAGE_LABELS.get(image.type, "Photo")
            if len(title.machines) > 1 and machine is not rep:
                label = f"{label} · {machine.name}"
            gallery.append({"url": large, "thumb": image.url("medium"), "label": label})

    editions = [
        {
            "name": machine.name,
            "date": machine.manufacture_date.year if machine.manufacture_date else machine.year,
            "features": ", ".join(machine.edition_features) or "Standard",
            "url": machine_page_url(site_url, machine),
            "current": machine is rep,
        }
        for machine in title.machines
    ]

    links = [{"label": "Open Pinball Database", "url": opdb_url(rep), "note": "Full OPDB record"}]
    if rep.ipdb_id:
        links.append(
            {
                "label": "Internet Pinball Database",
                "url": f"https://www.ipdb.org/machine.cgi?id={rep.ipdb_id}",
                "note": "Photos, documents and history",
            }
        )
    if primer := next((m_.primer_url for m_ in title.machines if m_.primer_url), None):
        links.append(
            {"label": "Pinball Primer", "url": primer, "note": "Beginner's guide and rules"}
        )
    if rules := next((m_.rules_url for m_ in title.machines if m_.rules_url), None):
        links.append({"label": "Rules", "url": rules, "note": "Detailed rule sheet"})

    same_year = [
        card_view(t, site_url)
        for t in dataset.titles_by_year.get(title.year or 0, [])
        if t.group_id != title.group_id and t.representative.images
    ][:8]

    specs = [
        ("Manufacturer", rep.manufacturer_full or rep.manufacturer),
        ("Released", m["release_label"]),
        ("Type", TYPE_LABELS.get(rep.type or "")),
        ("Display", DISPLAY_LABELS.get(rep.display or "")),
        ("Players", rep.players),
        ("Era", m["era_label"]),
        ("OPDB id", rep.opdb_id),
    ]

    hero = base["images"]["backglass"] or base["images"]["any"]
    description = (
        f"{title.name} is a {m['release_label'] or ''} {m['type_label'] or 'pinball'} machine "
        f"by {rep.manufacturer_full or rep.manufacturer or 'an unknown maker'}."
    ).replace("  ", " ")
    return {
        **m,
        "description": description,
        "hero": hero,
        "gallery": gallery,
        "credits": base["credits"],
        "facts": base["facts"],
        "fun_fact": base["fun_fact"],
        "specs": [(k, v) for k, v in specs if v],
        "editions": editions,
        "links": links,
        "same_year": same_year,
        "same_year_count": base["same_year_count"],
        "page_url": base["links"]["page"],
    }
