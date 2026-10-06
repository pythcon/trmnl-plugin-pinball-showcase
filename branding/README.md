# Branding

The Pinball Showcase mark: a steel ball dropping between two flippers, in TRMNL's
black / white / red / yellow palette.

| File | Use |
|---|---|
| `logo.svg` | Colour tile: website, favicon, app icons, link-preview card |
| `logo-mono.svg` | One colour: TRMNL plugin icon and e-ink title bars |

Every derived asset comes from these two files:

```bash
uvx --with pillow --from playwright python branding/build.py
```

It writes, into `api/src/pinball_showcase/web/static/`: `logo.svg`, `favicon.svg`,
`favicon.ico` (16/32/48), `apple-touch-icon.png` (180, full bleed), `icon-192.png`,
`icon-512.png`, `icon-maskable-512.png` (80% safe zone) and `og-card.png` (1200x630
link preview); and into `plugin/assets/`: `icon.svg` and `icon.png` (upload the PNG as
the plugin icon on trmnl.com). The plugin's title-bar icon in `plugin/src/shared.liquid`
inlines `logo-mono.svg`.
