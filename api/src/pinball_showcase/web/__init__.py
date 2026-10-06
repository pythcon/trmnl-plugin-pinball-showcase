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
from ..models import Machine
from ..presenter import (
    DISPLAY_LABELS,
    build_showcase,
    machine_page_url,
    opdb_url,
)
from ..search import MAX_RESULTS, index_for, result_payload
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
                {"page_title": "Machine not found", "opdb_id": opdb_id},
                status=404,
            )
        view = machine_view(
            dataset, title, local_now(tz), base_url(request), dataset.lookup_edition(opdb_id)
        )
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


def _first(title: Title, attr: str) -> str | None:
    return next(
        (getattr(m, attr) for m in (title.representative, *title.machines) if getattr(m, attr)),
        None,
    )


def _resources(title: Title) -> list[dict[str, str]]:
    rep = title.representative
    links = [
        {
            "label": "Open Pinball Database",
            "url": opdb_url(rep),
            "note": "The full OPDB record this page is built from",
        }
    ]
    if rep.ipdb_id:
        links.append(
            {
                "label": "Internet Pinball Database",
                "url": f"https://www.ipdb.org/machine.cgi?id={rep.ipdb_id}",
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
        if url := _first(title, attr):
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

    # Every photo across every edition, representative first, primary photos first.
    gallery: list[dict[str, Any]] = []
    seen: set[str] = set()
    for machine in (rep, *(x for x in title.machines if x is not rep)):
        for image in sorted(machine.images, key=lambda i: (not i.primary, i.type)):
            large = image.url("large")
            if not large or large in seen:
                continue
            seen.add(large)
            kind = IMAGE_LABELS.get(image.type, "Photo")
            caption = image.title if image.title and image.title.lower() != kind.lower() else kind
            width, height = image.sizes.get("large", (0, 0))
            gallery.append(
                {
                    "url": large,
                    "thumb": image.url("medium") or large,
                    "label": caption,
                    "edition": labels.get(machine.opdb_id),
                    "orientation": "portrait" if height > width else "landscape",
                }
            )

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
        display = m["display_label"].lower()
        article = "an" if display[0] in "aeiou" else "a"
        summary += f" It has {article} {display} display and plays up to {m['players_label']}."
    return {
        **m,
        "summary_text": summary,
        "description": _first(title, "description") or summary,
        "hero": hero,
        "gallery": gallery,
        "credits": base["credits"],
        "facts": base["facts"],
        "fun_fact": base["fun_fact"],
        "glance": [(k, v) for k, v in glance if v not in (None, "", 0)],
        "features": features,
        "editions": editions,
        "aliases": list(title.aliases),
        "resources": _resources(title),
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
