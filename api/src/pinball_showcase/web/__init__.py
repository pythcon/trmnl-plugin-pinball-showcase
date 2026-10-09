"""Public website: today's machine, recent picks, and a page for every machine.

The QR code on the TRMNL screen links to ``/m/{opdb_id}``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..config import Settings
from ..dataset import Dataset, Title
from ..models import Machine
from ..presenter import (
    DISPLAY_LABELS,
    build_showcase,
    machine_page_url,
    opdb_url,
)
from ..search import MAX_RESULTS, index_for, result_payload
from ..selection import Filters, PickMemo, Rotation, choose, period_key
from . import seo

HERE = Path(__file__).parent
STATIC_DIR = HERE / "static"


def _asset_version() -> str:
    """Content hash of the static files: changes whenever any of them does, so ?v= URLs
    and the service worker's caches roll over on every deploy that touches them."""
    digest = hashlib.sha256()
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(STATIC_DIR).as_posix().encode())
            digest.update(path.read_bytes())
    return f"{__version__}-{digest.hexdigest()[:10]}"


ASSET_VERSION = _asset_version()
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

# Gallery order within an edition: the art people know a machine by first.
_IMAGE_ORDER = {"backglass": 0, "playfield": 1, "cabinet": 2, "closeup": 3, "other": 4}


def _gallery(title: Title, shown: Machine, labels: dict[str, str]) -> list[dict[str, Any]]:
    """Every photo of every edition: the shown edition's first, then the others in edition
    order; within an edition backglass, playfield, cabinet, close-ups. Duplicate files
    (OPDB reuses images across editions) appear once, under the first edition that has them.
    """
    order = {entry["id"]: i for i, entry in enumerate(title.edition_list(shown))}
    machines = sorted(
        title.machines,
        key=lambda m: (m.opdb_id != shown.opdb_id, order.get(m.opdb_id, len(order))),
    )
    photos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for machine in machines:
        ranked = sorted(machine.images, key=lambda i: (_IMAGE_ORDER.get(i.type, 9), not i.primary))
        for image in ranked:
            large = image.url("large")
            if not large or large in seen:
                continue
            seen.add(large)
            kind = IMAGE_LABELS.get(image.type, "Photo")
            caption = image.title if image.title and image.title.lower() != kind.lower() else kind
            width, height = image.sizes.get("large", (0, 0))
            medium_width, _ = image.sizes.get("medium", (0, 0))
            photos.append(
                {
                    "url": large,
                    "medium": image.url("medium") or large,
                    "thumb": image.url("small") or image.url("medium") or large,
                    "width": width,
                    "height": height,
                    "medium_width": medium_width,
                    "label": caption,
                    "edition": labels.get(machine.opdb_id),
                    "other_edition": machine.opdb_id != shown.opdb_id,
                    "orientation": "portrait" if height > width else "landscape",
                }
            )
    return photos


templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["edition_phrase"] = lambda label: (
    label if label.lower().endswith("edition") else f"{label} edition"
)
templates.env.globals.update(
    more_plugins_url=MORE_PLUGINS_URL,
    github_url=GITHUB_URL,
    version=ASSET_VERSION,
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
        site = base_url(request)
        context = {
            "site_url": site,
            "default_og_image": seo.default_image(site),
            "structured_data": seo.json_ld(seo.website(site)),
            **context,
        }
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

        # What the daily rotation actually showed (the rotation memory), newest first.
        memo = get_memo()
        recent = []
        for days_back in range(1, RECENT_DAYS + 1):
            then = now - timedelta(days=days_back)
            shown = memo.get(f"daily:{period_key(then, Rotation.DAILY)}", Filters())
            past = dataset.by_group.get(shown) if shown else None
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
                "canonical": f"{site}/",
                "og_image": seo.machine_image(today),
                "structured_data": seo.json_ld(seo.website(site), seo.machine(site, today)),
            },
        )

    @router.get("/search", response_class=HTMLResponse)
    def search_page(request: Request, q: str = "") -> HTMLResponse:
        """Full results page: the no-JavaScript fallback for the header search."""
        dataset = dataset_or_503()
        query = q.strip()[:80]
        results = index_for(dataset).search(query, MAX_RESULTS) if query else []
        response = render(
            request,
            "search.html",
            {
                "page_title": f"Search: {query}" if query else "Search",
                "query": query,
                "search_query": query,
                "results": [result_payload(r) for r in results],
                "catalog_size": len(index_for(dataset)),
                "canonical": f"{base_url(request)}/search",
                "robots": "noindex, follow",
            },
        )
        response.headers["X-Robots-Tag"] = "noindex"
        return response

    @router.get("/m/{opdb_id}", response_class=HTMLResponse)
    def machine_page(request: Request, opdb_id: str, tz: str | None = None) -> HTMLResponse:
        dataset = dataset_or_503()
        title = dataset.lookup(opdb_id)
        if title is None:
            return render(
                request,
                "not_found.html",
                {"page_title": "Machine not found", "opdb_id": opdb_id, "robots": "noindex"},
                status=404,
            )
        site = base_url(request)
        view = machine_view(dataset, title, local_now(tz), site, dataset.lookup_edition(opdb_id))
        return render(
            request,
            "machine.html",
            {
                "m": view,
                "page_title": (
                    f"{view['name']} {view['edition_label']} ({view['headline']})"
                    if view["edition_label"]
                    else f"{view['name']} ({view['headline']})"
                ),
                "page_description": view["description"],
                "canonical": view["page_url"],
                "og_type": "article",
                "og_image": seo.machine_image(view),
                "structured_data": seo.json_ld(
                    seo.website(site),
                    seo.breadcrumbs(site, (view["name"], view["page_url"])),
                    seo.machine(site, view),
                ),
            },
        )

    # ---- Crawlers, install and offline ------------------------------------------------

    @router.get("/robots.txt", response_class=PlainTextResponse)
    def robots(request: Request) -> PlainTextResponse:
        return PlainTextResponse(seo.robots_txt(base_url(request)), headers=_day_cache)

    @router.get("/sitemap.xml")
    def sitemap(request: Request) -> Response:
        xml = seo.sitemap_xml(base_url(request), dataset_or_503())
        return Response(xml, media_type="application/xml", headers=_day_cache)

    @router.get("/manifest.webmanifest")
    def manifest() -> JSONResponse:
        return JSONResponse(
            seo.manifest(ASSET_VERSION),
            media_type="application/manifest+json",
            headers=_day_cache,
        )

    @router.get("/sw.js")
    def service_worker() -> Response:
        script = (STATIC_DIR / "sw.js").read_text().replace("__VERSION__", ASSET_VERSION)
        # Browsers re-check the worker on every navigation; never let a cache pin it.
        return Response(
            script,
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @router.get("/offline", response_class=HTMLResponse)
    def offline(request: Request) -> HTMLResponse:
        return render(
            request,
            "offline.html",
            {"page_title": "You're offline", "robots": "noindex"},
        )

    # Browsers and iOS ask for these at the site root regardless of <link> tags.
    for name in ("favicon.ico", "apple-touch-icon.png", "apple-touch-icon-precomposed.png"):
        target = "apple-touch-icon.png" if name.startswith("apple") else name

        def icon(target: str = target) -> FileResponse:
            return FileResponse(STATIC_DIR / target, headers=_week_cache)

        router.add_api_route(f"/{name}", icon, methods=["GET"], include_in_schema=False)

    return router


_day_cache = {"Cache-Control": "public, max-age=86400"}
_week_cache = {"Cache-Control": "public, max-age=604800"}


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


FEATURE_GROUPS = {
    "game": "Gameplay",
    "appearance": "Cabinet",
    "edition": "Editions",
    "other": "Other",
}


def _github_page(url: str) -> str:
    """raw.githubusercontent.com/<o>/<r>/refs/heads/<b>/<path> -> github.com/<o>/<r>/blob/<b>/<path>."""
    prefix = "https://raw.githubusercontent.com/"
    if not url.startswith(prefix):
        return url
    owner, repo, *rest = url[len(prefix) :].split("/")
    if rest[:2] == ["refs", "heads"]:
        rest = rest[2:]
    return f"https://github.com/{owner}/{repo}/blob/{'/'.join(rest)}"


def _resources(title: Title, rep: Machine) -> list[dict[str, str]]:
    ipdb_id = title.fill(rep, "ipdb_id")
    links = [
        {
            "label": "Open Pinball Database",
            "url": opdb_url(rep),
            "note": "The full OPDB record this page is built from",
        }
    ]
    if ipdb_id:
        links.append(
            {
                "label": "Internet Pinball Database",
                "url": f"https://www.ipdb.org/machine.cgi?id={ipdb_id}",
                "note": "Production history, documents and more photos",
            }
        )
    for attr, label, note, github in [
        ("primer_url", "Pinball Primer", "Beginner-friendly overview and strategy", False),
        ("rules_url", "Rule sheet", "Detailed rules from the community", False),
        ("bobs_guide_url", "Bob's Guide", "Machine guide and photos", False),
        ("cards_url", "Pinball Cards", "Collectible card for this machine", False),
        ("competition_notes_url", "Tournament notes", "How it plays in competition", True),
        ("competition_setup_url", "Tournament setup", "Recommended competition settings", True),
    ]:
        if url := title.fill(rep, attr):
            links.append(
                {"label": label, "url": _github_page(url) if github else url, "note": note}
            )
    return links


def machine_view(
    dataset: Dataset,
    title: Title,
    now: datetime,
    site_url: str,
    edition: Machine | None = None,
) -> dict[str, Any]:
    """Everything OPDB knows about a title, organised for the profile page.

    `edition` (from an edition id in the URL) is the version shown; otherwise the
    title's best one.
    """
    base = build_showcase(
        dataset,
        title,
        local_now=now,
        rotation=Rotation.DAILY,
        filters=Filters(),
        pool_size=1,
        period=now.date().isoformat(),
        site_url=site_url,
        edition=edition,
    )
    m = base["machine"]
    rep = edition or title.representative
    multi = len(title.versions) > 1
    labels = title.edition_labels() if multi else {}

    gallery = _gallery(title, rep, labels)

    features: dict[str, list[str]] = {}
    for machine in title.machines:
        for name, group in machine.features:
            if group == "edition":  # covered by the Editions section
                continue
            names = features.setdefault(FEATURE_GROUPS.get(group, "Other"), [])
            if name not in names:
                names.append(name)

    # Same labels as the device ("Standard", "CE", "LE"); OPDB's own edition flags are
    # inconsistent, so they're not shown.
    by_id = {machine.opdb_id: machine for machine in title.machines}
    editions = []
    for entry in title.edition_list(rep):
        machine = by_id[entry["id"]]
        editions.append(
            {
                "name": machine.name,
                "url": f"/m/{machine.opdb_id}",
                "released": _release(machine),
                "display": DISPLAY_LABELS.get(machine.display or "", "—"),
                "players": machine.players or "—",
                "features": entry["label"],
                "photos": len(machine.images),
                "current": entry["shown"],
            }
        )

    position = dataset.manufacturer_position(title)
    glance = [
        ("Released", m["release_label"]),
        ("Type", m["type_label"]),
        ("Display", m["display_label"]),
        ("Players", rep.players),
        ("Era", m["era_label"]),
        ("Editions", len(title.versions)),
        ("Photos", len(gallery)),
        (f"{rep.manufacturer} catalogue", f"#{position[0]} of {position[1]}" if position else None),
    ]

    same_year = [
        card_view(t, site_url)
        for t in dataset.titles_by_year.get(title.year or 0, [])
        if t.group_id != title.group_id and t.representative.images
    ][:12]

    # Same rule as the device: this edition's own photo first; a borrowed one is captioned.
    hero = base["images"]["any"]
    maker = rep.manufacturer_full or rep.manufacturer or "an unknown maker"
    summary = (
        f"{title.name} is a {(m['type_label'] or 'pinball').lower()} pinball machine by {maker}"
    )
    if m["release_label"]:
        summary += f", released {m['release_label']}"
    summary += "."
    if m["display_label"] and rep.players:
        # "an LCD", "a CGA monitor", "an alphanumeric": acronyms keep their case and
        # take the article of their spoken first letter.
        label = m["display_label"]
        acronym = label.split()[0].isupper()
        display = label if acronym else label.lower()
        article = "an" if display[0] in ("AEFHILMNORSX" if acronym else "aeiou") else "a"
        summary += f" It has {article} {display} display and plays up to {m['players_label']}."
    return {
        **m,
        "summary_text": summary,
        "release_iso": seo.release_iso(rep.manufacture_date),
        "description": title.fill(rep, "description") or summary,
        "hero": hero,
        "gallery": gallery,
        "credits": base["credits"],
        "facts": base["facts"],
        "fun_fact": base["fun_fact"],
        "glance": [(k, v) for k, v in glance if v not in (None, "", 0)],
        "features": features,
        "editions": editions,
        "aliases": list(title.aliases),
        "resources": _resources(title, rep),
        "same_year": same_year,
        "same_year_count": base["same_year_count"],
        "page_url": base["links"]["page"],
        "opdb_url": base["links"]["opdb"],
    }


def _release(machine: Any) -> str:
    d = machine.manufacture_date
    if d is None:
        return str(machine.year or "—")
    if d.month == 1 and d.day == 1:
        return str(d.year)
    return f"{d:%b} {d.year}" if d.day == 1 else f"{d:%b} {d.day}, {d.year}"
