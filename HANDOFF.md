# Handoff: Pinball Showcase (as of 2026-10-09)

Read `CLAUDE.md` first (project rules), then this file. Everything below is either
**pending work** (do it) or **context you'd otherwise rediscover the hard way**.

## Where things stand

- **Live:** API + website at https://pinball-showcase.trmnlplugins.com (master `eb4e6dd`),
  deployed by `.github/workflows/api.yml` on push (self-hosted runner, SSH deploy; see
  `deploy/DEPLOYMENT.md`). All tests green: `make check` (105 API tests, 272 plugin
  render checks).
- **TRMNL plugin:** private plugin id **497284** (`plugin/src/settings.yml` has the id).
  On the owner's devices TRMNLBWRY1 (id 56826) and TRMNLX1 (id 51325). Not yet published
  as a recipe. Owner's instance is on defaults (daily rotation, no pin, no filters).
- **The plugin on trmnl.com is behind the repo.** The last upload was `598f383`. Not yet
  uploaded: the short edition labels in half/quadrant layouts (`e792d2a`) and the Spec
  Sheet fix (`eb4e6dd`). Uploading is task 1.

## Tasks, in order

### 1. Get plugin uploads off the chat connector (automatic push from CI)

The TRMNL MCP connector in Claude Code keeps dropping ("Tool not found"), and uploads via
MCP (`AccountPluginSettingsTool` → `importPluginSettingFiles`) need every file inline,
`settings.yml` included, on every call. Replace that with CI:

- `.github/workflows/plugin.yml` already has a `push` job (`trmnlp push --force`) gated on
  the repo variable `TRMNL_PUSH == 'true'` and the secret `TRMNL_API_KEY`.
- **Owner action:** add the TRMNL account API key (trmnl.com/account) with
  `gh secret set TRMNL_API_KEY`. Then `gh variable set TRMNL_PUSH --body true`.
- Verify with a no-op plugin commit (or `workflow_dispatch`): lint → test → push succeed,
  and `AccountPluginSettingsTool getPluginSettingFiles` (if the connector works) or the
  trmnl.com editor shows the repo's markup. Then refresh the plugin and check the BWRY
  and X devices.
- Confirm `trmnlp push --force` keeps the plugin **id 497284** and its custom-field values
  (the owner's instance settings) intact. If it would create a new plugin or reset values,
  stop and ask.

### 2. Self-maintaining dropdown options (owner: "I don't want to maintain any options, but
want multi-select")

Agreed design: keep `field_type: select` + `multiple: true`, and have a **scheduled
workflow** regenerate the data-driven option lists in `plugin/src/settings.yml` from the
live API, commit only when something changed, and let task 1's CI push it to TRMNL.

- Source: `GET https://pinball-showcase.trmnlplugins.com/api/v1/options`. It returns,
  per filter, `[{value, titles}]` counted over showcase-ready titles (currently
  120 manufacturers; decades 1940-2020; displays; players 1/2/4/6; eras; features;
  rotation). Values are what the API's filters accept.
- **Sync these fields:** `manufacturers`, `exclude_manufacturers` (must be identical lists),
  `decades`, `displays`, `players`, `eras`, `features`, `exclude_features` (identical).
- **Rules:**
  - Options use the mapping form `- "Label": "value"` with quoted values. TRMNL stores a
    quoted `"Label: value"` string literally (see Gotchas); keep the quotes so values like
    `on`/`1930` stay strings.
  - Manufacturer value = lowercase OPDB name (the API matches known maker names exactly,
    see `selection.py` `_maker_matches`); label = OPDB name as is. Alphabetical.
  - Drop options with `titles == 0` (today the hand-made list offers **1930s, which
    matches nothing**).
  - **No counts in labels** ("Stern", not "Stern (81)"): counts change daily and would
    cause a commit + TRMNL upload every day. The list should only change when a maker,
    decade etc. appears or disappears.
  - Labels for coded values come from a small map in the sync script (e.g. `dmd` → "Dot
    matrix", `early_ss` → "Early solid state (alphanumeric, lights)", features keep their
    current labels); unknown values get a readable fallback (title-case, `_` → space).
    Better: have the API return a `label` per option and use it, so labels live in one place.
- **Keep static** (plugin's own presentation): `display_mode`, `art_*`, `art_fit`,
  `art_position`, `hide_details`, `color_accents`, `require_playfield`. `rotation` stays
  hand-written (each option has an explanation) but add a test that fails if its values
  differ from the API's `rotation` list.
- Free-text fields stay free text: `other_manufacturers`, `keywords`, `exclude_keywords`,
  `people`, `favorites`, `pinned_machine`, `exclude_ids`.
- Implementation sketch: `plugin/bin/sync-options` (Python, stdlib only) that rewrites
  only the `options:` blocks of the named fields, preserving everything else in
  `settings.yml` byte for byte; `make sync-options`; workflow `.github/workflows/options.yml`
  on `schedule` (daily, after the OPDB refresh at 04:00 UTC, e.g. `0 6 * * *`) +
  `workflow_dispatch`, self-hosted, that runs it, then `make plugin-lint plugin-test`, and
  commits + pushes only on a diff. The push triggers the plugin workflow (task 1).
  Also add a unit/CI check that the synced lists equal the API's.
- Unknown: whether users who already installed the published recipe receive updated option
  lists. Note it in the PR; the free-text "Other Manufacturers" field covers stale lists.
- Alternative considered: `field_type: xhrSelect` (options fetched from a URL, docs in the
  trmnl skill `references/template_guide.md` ~line 2658). Docs only describe single choice.
  If you can verify (MCP `AccountPluginSettingsTool verifyCustomFields`) that it accepts
  `multiple: true`, it would remove the sync job entirely; otherwise don't use it.

### 3. Make it obvious every setting is optional

Owner: "make it very easy for users to see all the options are optional… descriptions
should start with 'Optional'." Every field already has `optional: true`, but TRMNL's form
doesn't make that obvious.

- Start every custom-field `description` with **"Optional."** and then say what happens
  when it's left empty, e.g.:
  - Eras: "Optional. Leave empty for every era."
  - Manufacturers: "Optional. Show only these makers; leave empty for all."
  - Photos - Full Screen: "Optional. Leave empty to choose automatically…"
  - Pin One Machine: "Optional. Always show this machine instead of rotating…"
  - Fields that currently have no description (`art_fit`, `art_position`, `color_accents`,
    `eras`, `decades`, `min_year`, `max_year`, `exclude_manufacturers`, `exclude_keywords`,
    `displays`, `players`, `exclude_features`, `require_playfield`) need one written.
- Consider also stating it once in the `about` (author_bio) description: "Every setting is
  optional; with none set you get a new machine from the whole catalogue each day."
- Optional extra the owner was offered but didn't answer: one line in `about` explaining that
  the title at the bottom of the screen is the plugin's **Name** (top of its settings), so
  renaming the plugin changes it. Ask before adding.
- The sync script (task 2) must preserve these descriptions.

### 4. Publish checklist (owner does these on trmnl.com)

1. Upload the plugin icon: `plugin/assets/icon.png` (one-colour mark; no API for icons).
2. Check the featured image shows the Harry Potter CE screen. It was generated via
   `setPluginSettingFeaturedImage` while that machine was pinned; the API can't confirm
   the result. If wrong: pin `GWyBj-MdEbK-AOPdq`, regenerate, then reset the pin.
3. Publish as a recipe. Its automated hints ("missing title_bar include", "no layout
   class") are false positives: each view has `<div class="layout …">` and a sibling
   `<div class="title_bar">` (framework v3); `shared.liquid` has neither by design.

## Gotchas (learned the hard way)

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
