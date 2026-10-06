# TRMNL Pinball Showcase

A different pinball machine on your [TRMNL](https://trmnl.com) every day: backglass and
playfield art dithered for e-ink, release details, designers and artists, editions, fast
facts and a QR code to the full entry, all from the
[Open Pinball Database (OPDB)](https://opdb.org).

Works on **TRMNL OG** (1-bit and 2-bit), **TRMNL X** and **color B/W/R/Y** panels, in all
four mashup sizes, landscape and portrait.

## Features

**On screen**
- Machine of the day (or of the 12 hours, 6 hours or hour), the same on every device
- Photos chosen per layout size: backglass, playfield and/or cabinet. Pick one, several
  side by side (up to 3 full screen, 2 in halves, 1 in a quadrant), none for text only, or
  leave empty for auto (backglass; playfield in the tall half-vertical slot). Missing photos are skipped
- Photo style: fit (whole photo) or fill (cropped to the space), and artwork on the left or right (top or bottom)
- Manufacturer, exact release date when known, type, score display, player count
- Edition and feature tags (Pro, Premium/LE, Remake, Widebody...)
- Credits: design, art, code, mechanics, animation, music and sound
- Fast facts: age, era, place in its maker's catalogue, how many titles shipped that year
- A fun fact, including a "happy birthday" on a machine's release anniversary
- Other titles from the same year (Spec Sheet layout on TRMNL X)
- QR code to the machine's OPDB page
- Three layouts: **Showcase** (art and details), **Gallery** (art first), **Spec Sheet** (details first)
- Anything optional can be hidden; color accents can be turned off

**Choosing machines** (every filter takes any number of values; values within a filter
are OR'd, different filters are AND'd)
- Eras: electro-mechanical, early solid state, dot matrix, modern LCD
- Decades and/or a from–to year range
- Manufacturers to include and exclude: pick from the 39 biggest makers (exact match, so Stern
  doesn't pull in Stern Electronics) and/or type any others
- Title keywords to include and exclude (themes: "star wars, batman, monster")
- Designers and artists (anyone credited)
- Score display: reels, backbox lights, alphanumeric, DMD, LCD, CGA
- Player count
- Features to require or exclude: widebody, cocktail, add-a-ball, replay, head-to-head,
  multiple editions, Pro, Premium, LE, remake, vault, home, export, conversion kit
- Only machines with playfield photos
- A favorites list to rotate through, a never-show list, or pin a single machine
- No repeats: every machine in your selection is shown once before any comes back, and never twice in a row

**Device support**
- Device-aware styling: real red/yellow accents on color panels, gray mappings on
  grayscale, and plain black-on-white on the 1-bit OG (gray text would become noise)
- `lg:` layouts use TRMNL X's extra room for more credits, facts and bigger type
- Graceful states for "no matches" and "API unreachable"

## How it works

```
OPDB daily export ──(07:00 UTC, conditional GET)──▶ API container ──▶ /data cache
  (Match Play CDN)                                       │
                                                         ▼
TRMNL ──polls──▶ GET /api/v1/showcase?filters… ──▶ JSON merge variables ──▶ Liquid templates
```

- **`api/`**: FastAPI service. Downloads the OPDB export once a day, groups editions
  into titles, filters, picks the featured machine and returns a flat JSON payload.
- **`plugin/`**: the TRMNL plugin (a [trmnlp](https://github.com/usetrmnl/trmnlp) project):
  Liquid layouts, `settings.yml` with all the custom fields, and render tests.
- **`deploy/`**: production compose file, Caddy config and the [deployment plan](deploy/DEPLOYMENT.md).

## Using it

Install **Pinball Showcase** from TRMNL (or import `plugin/` as a private plugin), pick
your layout and filters, and you're done. It polls the hosted API at
`https://pinball.trmnlplugins.com`. No keys or accounts needed.

## Self-hosting

The API is one small container with no secrets:

```bash
docker compose up -d          # uses ghcr.io/pythcon/trmnl-plugin-pinball-showcase
curl localhost:8080/readyz    # ready once the export is loaded (a few seconds)
```

Then set **Self-hosted API URL** in the plugin's settings to your address (it must be
reachable from TRMNL's servers). Every
setting is optional; see [`.env.example`](.env.example).

Without Docker: `cd api && uv run pinball-showcase` (Python 3.12+).

## API

Interactive docs at `/docs`.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/showcase` | The featured machine for the current period (the TRMNL polling target) |
| `GET /api/v1/machines/{opdb_id}` | Payload for any machine, group or alias id |
| `GET /api/v1/options` | Every filter value with title counts (manufacturers, decades, features...) |
| `GET /api/v1/dataset` | Cached export info: size, fetched at, next refresh, last error |
| `GET /healthz`, `GET /readyz` | Liveness and readiness |

`/api/v1/showcase` parameters (all optional; multi-value ones accept commas or repeats):

| Param | Example |
|---|---|
| `rotation` | `daily` (default), `12h`, `6h`, `hourly` |
| `tz` | `America/New_York` (when the day/hour rolls over) |
| `machine` | `G5pe4` pins one machine |
| `favorites`, `exclude_id` | `G5pe4,GrqZX` |
| `era` | `em`, `early_ss`, `dmd`, `modern` (`ss` = all solid state) |
| `decade` | `1970,1990s` |
| `min_year`, `max_year` | `1978`, `1999` |
| `manufacturer`, `exclude_manufacturer` | `williams,bally` |
| `keyword`, `exclude_keyword` | `star wars,batman` |
| `person` | `steve ritchie,pat lawlor` |
| `display` | `reels,alphanumeric,lights,dmd,lcd,cga` |
| `players` | `1,2,4` |
| `feature`, `exclude_feature` | `widebody,remake,multi_edition` |
| `require_playfield` | `true` |
| `date` | `2026-10-05` (preview another day) |

## Development

```bash
make help            # all tasks
make api-dev         # API with reload on :8080
make api-test        # pytest
make plugin-lint     # trmnlp lint
make preview         # virtual TRMNL at http://localhost:4567 backed by the local API
make plugin-test     # render every view on OG / OG 2-bit / X / portrait / B/W/R/Y
open plugin/report/index.html
make fixtures        # refresh plugin test fixtures from today's export
make check           # what CI runs
```

Plugin tests use real API responses saved in `plugin/tests/fixtures`, so they run offline.

The local viewer is accurate for OG-size screens. For TRMNL X it shows a cropped corner:
TRMNL renders X at 1.8x scale, which the viewer's browser frame doesn't reproduce. With
`make preview` running, `make preview-x` renders all four views at X's real resolution and
opens them (`ORIENTATION=portrait make preview-x` for portrait).
`trmnlp` renders grayscale only; check true color output on a B/W/R/Y device or with the
TRMNL MCP screenshot tool (`device_models: ["og_bwry"]`).

### Repository layout

```
api/                     FastAPI service (uv project)
  src/pinball_showcase/  config, OPDB parsing, filters/selection, payload, HTTP app
  tests/                 pytest suite
  scripts/               fixture refresh
  Dockerfile
plugin/                  TRMNL plugin (trmnlp project)
  src/                   full / half_horizontal / half_vertical / quadrant / shared .liquid, settings.yml
  tests/                 render tests + fixtures
deploy/                  production compose, Caddyfile, DEPLOYMENT.md
compose.yaml             self-hosting
.github/workflows/       API (test, image, optional deploy) and Plugin (lint, render, optional push)
```

## Data

Machine data and images come from the [Open Pinball Database](https://opdb.org), via the
daily export published by [Match Play Events](https://docs.matchplay.events/data-exports).
Please credit OPDB if you build on this. The plugin shows "OPDB" on every screen.

## License

MIT
