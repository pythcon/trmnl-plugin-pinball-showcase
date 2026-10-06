"""Search engines, link previews and the installable app: structured data, sitemap,
robots.txt, the web app manifest and the service worker."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from xml.sax.saxutils import escape

from ..dataset import Dataset
from ..presenter import machine_page_url

SITE_NAME = "Pinball Showcase"
TAGLINE = "A different pinball machine on your TRMNL every day."
THEME_LIGHT = "#fbfaf6"
THEME_DARK = "#101010"
BRAND_INK = "#141414"
OG_CARD = {"path": "/static/og-card.png", "width": 1200, "height": 630}


def absolute(site: str, path: str) -> str:
    return path if path.startswith(("http://", "https://")) else f"{site.rstrip('/')}{path}"


def default_image(site: str) -> dict[str, Any]:
    return {
        "url": absolute(site, OG_CARD["path"]),
        "width": OG_CARD["width"],
        "height": OG_CARD["height"],
        "alt": f"{SITE_NAME}: {TAGLINE}",
        "type": "image/png",
    }


def machine_image(view: dict[str, Any]) -> dict[str, Any] | None:
    """The machine's own art for link previews (OPDB's large photo, ~1200px)."""
    hero = view.get("hero")
    if not hero or not hero.get("url"):
        return None
    edition = f" {view['edition_label']}" if view.get("edition_label") else ""
    return {
        "url": hero["url"],
        "width": hero.get("width") or None,
        "height": hero.get("height") or None,
        "alt": f"{view['name']}{edition} pinball artwork",
        "type": "image/jpeg",
    }


def json_ld(*blocks: dict[str, Any]) -> str:
    """Serialised for a <script type="application/ld+json">; '</' can't end the tag."""
    data = (
        blocks[0]
        if len(blocks) == 1
        else {"@context": "https://schema.org", "@graph": list(blocks)}
    )
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def website(site: str) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": f"{site}/#website",
        "name": SITE_NAME,
        "description": TAGLINE,
        "url": f"{site}/",
        "inLanguage": "en",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{site}/search?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def breadcrumbs(site: str, *items: tuple[str, str]) -> dict[str, Any]:
    trail = [("Pinball Showcase", f"{site}/"), *items]
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": url}
            for i, (name, url) in enumerate(trail, start=1)
        ],
    }


def machine(site: str, view: dict[str, Any]) -> dict[str, Any]:
    """A pinball machine as a schema.org Product (it's a manufactured product line)."""
    name = view["name"] + (f" ({view['edition_label']})" if view.get("edition_label") else "")
    maker = view.get("manufacturer_full") or view.get("manufacturer")
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "@id": f"{view['page_url']}#machine",
        "name": name,
        "url": view["page_url"],
        "description": view.get("description") or view.get("summary_text"),
        "category": "Pinball machine",
        "sku": view["id"],
        "image": [g["url"] for g in view.get("gallery", [])[:6]] or None,
        "sameAs": [view["opdb_url"]],
    }
    if maker:
        data["brand"] = {"@type": "Brand", "name": view.get("manufacturer") or maker}
        data["manufacturer"] = {"@type": "Organization", "name": maker}
    if view.get("release_iso"):
        data["releaseDate"] = view["release_iso"]
    properties = [
        ("Type", view.get("type_label")),
        ("Display", view.get("display_label")),
        ("Players", view.get("players")),
        ("Edition", view.get("edition_label")),
    ]
    data["additionalProperty"] = [
        {"@type": "PropertyValue", "name": k, "value": v} for k, v in properties if v
    ]
    return {k: v for k, v in data.items() if v not in (None, [], "")}


def robots_txt(site: str) -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /search\n"
        "Disallow: /api/\n"
        "\n"
        f"Sitemap: {site}/sitemap.xml\n"
    )


def sitemap_xml(site: str, dataset: Dataset) -> str:
    """Every machine page: each title's default page and each edition with its own page."""
    lastmod = dataset.fetched_at.date().isoformat()
    urls: list[tuple[str, str]] = [(f"{site}/", "daily")]
    seen: set[str] = set()
    for title in dataset.showcase_titles:
        for edition in (title.representative, *title.versions):
            url = machine_page_url(site, edition)
            if url not in seen:
                seen.add(url)
                urls.append((url, "monthly"))
    rows = "".join(
        f"<url><loc>{escape(loc)}</loc><lastmod>{lastmod}</lastmod><changefreq>{freq}</changefreq></url>"
        for loc, freq in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>\n'
    )


def manifest(version: str) -> dict[str, Any]:
    return {
        "id": "/",
        "name": SITE_NAME,
        "short_name": "Pinball",
        "description": TAGLINE,
        "lang": "en",
        "dir": "ltr",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "display_override": ["standalone", "minimal-ui"],
        "orientation": "any",
        "background_color": THEME_LIGHT,
        "theme_color": BRAND_INK,
        "categories": ["entertainment", "games", "reference"],
        "icons": [
            {
                "src": f"/static/icon-192.png?v={version}",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": f"/static/icon-512.png?v={version}",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": f"/static/icon-maskable-512.png?v={version}",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
            {
                "src": f"/static/logo.svg?v={version}",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
        ],
        "shortcuts": [
            {
                "name": "Pinball of the Day",
                "short_name": "Today",
                "url": "/?source=pwa-shortcut",
                "icons": [{"src": f"/static/icon-192.png?v={version}", "sizes": "192x192"}],
            },
            {
                "name": "Search machines",
                "short_name": "Search",
                "url": "/search?source=pwa-shortcut",
                "icons": [{"src": f"/static/icon-192.png?v={version}", "sizes": "192x192"}],
            },
        ],
    }


def release_iso(day: date | None) -> str | None:
    """OPDB stores year-only dates as January 1st; those are reported as just the year."""
    if day is None:
        return None
    return str(day.year) if (day.month, day.day) == (1, 1) else day.isoformat()
