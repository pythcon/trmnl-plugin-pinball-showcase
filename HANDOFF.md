# Handoff: Pinball Showcase (as of 2026-10-15)

Read `CLAUDE.md` first (project rules), then this file. Everything below is either
**pending work** (do it) or **context you'd otherwise rediscover the hard way**.

## Where things stand

- **Live:** API + website at https://pinball-showcase.trmnlplugins.com (master `eb4e6dd`),
  deployed by `.github/workflows/api.yml` on push (self-hosted runner, SSH deploy; see
  `deploy/DEPLOYMENT.md`). All tests green: `make check` (105 API tests, 272 plugin
  render checks).
- **TRMNL plugin:** private plugin id **497284** (`plugin/src/settings.yml` has the id).
  On the owner's devices TRMNLBWRY1 (id 56826) and TRMNLX1 (id 51325). Not yet published
  as a recipe. The owner's instance currently has test values (shuffle, JJP + Spooky,
  5 min refresh); that's their choice, don't reset it.
- **Plugin uploads are automatic:** `plugin.yml` runs `trmnlp push --force` after lint +
  test on every master push touching `plugin/**` (or Run workflow on master). Verified
  2026-10-09 (`9ea9a8b`): same plugin id, every file matches the repo, instance custom-field
  values kept. Don't upload via MCP any more.

## Tasks, in order

### ~~1. Automatic plugin push from CI~~ (done 2026-10-09)

`TRMNL_API_KEY` secret + `TRMNL_PUSH=true` variable are set. The push job uses the `id`
in `settings.yml`; the archive import keeps the instance's custom-field values.

### ~~2. Self-maintaining dropdown options~~ (done 2026-10-09)

`.github/workflows/options.yml` runs daily at 06:00 UTC (and on Run workflow):
`plugin/bin/sync-options` (`make sync-options`) rewrites only the `options:` lists of
`eras`, `decades`, `manufacturers`/`exclude_manufacturers`, `displays`, `players`,
`features`/`exclude_features` from `/api/v1/options`, drops options with 0 titles, then
lints/tests, commits as github-actions[bot] and dispatches `plugin.yml` to upload
(GITHUB_TOKEN pushes don't trigger workflows; a dispatch does). Labels come from the API
(`options.py`, every option has `label`, lists in a stable order, maker values
lowercase); the script only overrides two wordings (`LABELS`). `rotation` stays
hand-written; the script and `api/tests/test_sync_options.py` fail if it drifts from the
API. First sync `b191363`: 120 makers, 1930s dropped. Open question: whether users of an
already-installed recipe get updated option lists.

### ~~3. Make it obvious every setting is optional~~ (done 2026-10-15)

Every description starts with "Optional." and says what empty means; `about` says every
setting is optional. Not done (never answered): a line explaining that the bottom title is
the plugin's Name.

### ~~3b. TRMNL review round 1 (Mario, 2026-10-15)~~ (done, awaiting re-review)

- Settings in `group:` accordions (Photos, What to Show, Pick Machines, Era and Year,
  Manufacturer, Theme and People, Machine Type, Advanced); about, Layout Style and New
  Machine stay ungrouped. Grouped fields must stay contiguous in `settings.yml`.
- `lg:value--medium` (invalid) → `lg:value--base`. `rotation` defaults to `refresh`
  (the API still treats a blank rotation as daily). `require_playfield` is a `boolean`.
- TRMNL X layouts (approved mockup: https://claude.ai/artifact/7LS4rwwZmjdnbmNU9DnSE8):
  equal outlined stat tiles pinned above the title bar, with "Also released in YEAR" in
  the details column (Showcase; chosen 2026-10-15 over a strip and tiles-under-art), backglass+playfield pair (Gallery,
  automatic photos only), stats grid (Spec), all credits + stats (halves), summary +
  credits + fun fact (quadrant). All X-only (`hidden lg:…` / `lg:hidden`); OG unchanged.
- New payload field `stats` (`[{value, label}]`, the facts as big numbers).
- Tell Mario it's ready for another review once it's pushed and uploaded.

### 4. Publish checklist (owner does these on trmnl.com)

1. Upload the plugin icon: `plugin/assets/icon.png` (one-colour mark; no API for icons).
2. Check the featured image shows the Harry Potter CE screen. It was generated via
   `setPluginSettingFeaturedImage` while that machine was pinned; the API can't confirm
   the result. If wrong: pin `GWyBj-MdEbK-AOPdq`, regenerate, then reset the pin.
3. Publish as a recipe. Its automated hints ("missing title_bar include", "no layout
   class") are false positives: each view has `<div class="layout …">` and a sibling
   `<div class="title_bar">` (framework v3); `shared.liquid` has neither by design.

## Gotchas (learned the hard way)

- **TRMNL framework (`latest`) quirks on X**, found 2026-10-15:
  - `data-clamp` on a title measures at the OG size, so on X short names were cut
    ("Jurassic Pa…"). Full-screen titles clamp only when `long_name`.
  - `hidden lg:grid grid--cols-2` doesn't apply the columns; wrap the grid in a
    `hidden lg:block` div.
  - Inline `<span>`s inside a `label` break its line layout (words run together or
    stack); use separate `label` elements in a wrapping flex row.
  - Stats use `value--large` (Showcase) / `value--base` (elsewhere); `value--xlarge` is
    too big. `value--medium` isn't a valid responsive size.

- **Select options** must be YAML mappings `- "Label": "value"`. A quoted `"Label: value"`
  is stored as the literal value and filters silently stop working.
- `updatePluginSettingFields` values must be strings (multi-selects: `""` to clear).
- **MCP import** (`importPluginSettingFiles`) rejects calls without `settings.yml` and may
  drop files you don't send; always send every file.
- `trmnlp` renders B/W/R/Y in grayscale only. Real colour previews:
  `AccountMarkupTool startPreview` with `device_model: "og_bwry"`. On B/W/R/Y, **thin gray
  text on yellow vanishes**: text on a yellow callout must use the bold black `label`
  font (comment in `shared.liquid`).
- **Editions** (`api/src/pinball_showcase/editions.py`, `dataset.py`):
  - OPDB aliases are full editions; some titles' editions are all aliases of a photo-less
    "umbrella" machine (Harry Potter), which is skipped.
  - Labels come from names, never from OPDB's edition flags, with one exception: **SE** is
    read via the flag (Pro-flagged = Standard Edition, Spooky; Premium-flagged = Special
    Edition, Chicago Gaming's Pulp Fiction).
  - Long labels on the website and the full layout; short ones (`edition_short`, `short`)
    in half/quadrant.
  - Seven OPDB group names contain an edition ("(SE)", "(Home Edition)"); those suffixes
    are stripped and badged. "Centaur (Inder)" is not an edition and stays.
- **Missing edition data** is filled through `Title.lineage(shown)`: the edition, the
  machine it's an alias of, the title's default edition, then the rest. Credits fill per
  role and only from the same manufacturer (remakes filed under the original don't inherit
  its team); photos, IPDB id, description and resource links from any edition. Some
  titles have nothing to fill from: OPDB has no credits for 383 of 1612 titles (73 since
  2010, e.g. Toy Story 4, every edition), so empty credits there are a data gap.
- **Rotation** keeps a cursor per stream in `/data/rotation.json` (plus `picks.json`) so
  OPDB adding titles never causes repeats/skips. `?date=` previews are read-only. Everyone
  with the same filters sees the same machine per period; the owner chose this.
- **Layouts** use row budgets (Showcase and Spec Sheet in `full.liquid`, half-vertical
  credit lines) so nothing is cut off on OG; TRMNL X (`lg:`) shows everything. If you add
  rows, update the budget and look at `plugin/report/` screenshots.
- **Website:**
  - Strict CSP (`main.py`); add any new third-party origin there (Cloudflare analytics is
    allowed).
  - Static URLs and service-worker caches are keyed by a content hash (`ASSET_VERSION`).
  - Cloudflare proxies the site and caches 404s for `.ico`/`.png` for ~4 h. Purge after
    adding such routes.
- `git push` to GitHub has intermittently returned 500 Internal Server Error; it succeeded
  on retry a few minutes later.
- Port 8765 on the dev Mac belongs to another app; use a free port for local servers.
- Commit message trailer used in this repo:
  `Claude-Session: https://claude.ai/code/session_012t4SWvofWXJb7RFW5kPujN`

## Verify before you hand back

`make check`, look at `plugin/report/index.html` for the views you touched, push, confirm
the API workflow deploys, and spot-check https://pinball-showcase.trmnlplugins.com plus a
B/W/R/Y preview of the plugin.
