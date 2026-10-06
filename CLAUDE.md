# TRMNL Pinball Showcase

TRMNL plugin + self-hostable API showing a daily pinball machine from the OPDB export.

- `api/`: FastAPI (uv, Python 3.12+). `make api-test`, `make api-lint`. Selection logic in
  `selection.py` (multi-value filters, no-repeat shuffle, `PickMemo`), payload in `presenter.py`.
  Any new payload field must be reflected in `plugin/tests/fixtures` (`make fixtures`).
- `plugin/`: trmnlp project. Follow TRMNL framework v3 rules (load the `trmnl` skill): no
  inline styles/`<style>`, `image-dither` on artwork, `layout` + sibling `title_bar`, `lg:` for
  TRMNL X, arbitrary `w--[Npx]` only 0-128. `make plugin-lint && make plugin-test`, then look
  at `plugin/report/index.html`. trmnlp renders grayscale only; verify B/W/R/Y with the TRMNL
  MCP `MarkupsScreenshotTool` and `device_models: ["og_bwry"]`.
- Device styling is decided in `plugin/src/shared.liquid` (`is_mono`, `is_color`, `muted`,
  `accent_*`) from `trmnl.device.model`/`bit_depth`.
- Custom field keynames must not collide with payload keys (`machine`, `images`, `credits`,
  `facts`, `qr`, `featured`, `error`...).
- Deployment: `deploy/DEPLOYMENT.md`. Hosted at pinball.trmnlplugins.com; image on GHCR.
