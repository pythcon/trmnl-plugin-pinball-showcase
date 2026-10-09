---
name: prime
description: Primes Claude with full context on the Pinball Showcase TRMNL plugin at the start of a session. Loads the project rules and the open handoff, then checks git, CI, the live API and website, and the TRMNL plugin so Claude can pick up work immediately without Todd re-explaining the project.
allowed-tools: Bash, Read, Glob, Grep
---

# Prime: Pinball Showcase Session Bootstrap

## What is this project?

A **TRMNL e-ink plugin** that shows a different pinball machine every day, plus the
**API and public website** that power it. Data comes from the **OPDB daily export**
(Match Play CDN), downloaded once a day at midnight New York time.

- **API + website:** FastAPI container at https://pinball-showcase.trmnlplugins.com.
  It serves `/api/v1/showcase` (TRMNL polls this), a machine page per edition (`/m/{id}`,
  the QR code target), search, sitemap and a PWA. Self-hostable (`compose.yaml`).
- **Plugin:** a trmnlp project in `plugin/`. TRMNL private plugin **id 497284**, on Todd's
  devices TRMNLBWRY1 (B/W/R/Y colour, id 56826) and TRMNLX1 (TRMNL X, id 51325).
  Supports TRMNL OG, TRMNL X and B/W/R/Y in all four sizes. Layout styles: Showcase,
  Gallery, Spec Sheet. Not yet published as a recipe.
- **Hosting:** the existing TRMNL plugins server (shared with the Grafana plugin), behind
  host nginx + Cloudflare (proxied). Deployed by GitHub Actions on push to `master`
  (self-hosted runner, SSH with a deploy key, all targets in secrets).

## Step 1: Load the map

Read in full before doing anything else:

1. `CLAUDE.md`: project rules (TRMNL framework v3, payload/fixture contract, device styling).
2. `HANDOFF.md`: **open tasks in priority order** and the hard-won gotchas. If it has
   pending tasks, they are the default next work.
3. `deploy/DEPLOYMENT.md`: only if the task touches deploys, the server or secrets.
4. For plugin markup work, load the `trmnl` skill (framework v3 reference).

## Step 2: Live state (read-only, run in parallel)

```bash
# Git: branch, uncommitted work, recent history
git status -sb | head -20; git log --oneline -10

# CI: last runs of each workflow (API deploys, plugin lint/test/push)
gh run list -L 6 --json workflowName,headSha,status,conclusion,createdAt \
  -q '.[] | "\(.workflowName)\t\(.headSha[0:7])\t\(.status)\t\(.conclusion)\t\(.createdAt)"'

# Deployed API commit vs the last commit that touched the API (plugin-only commits
# don't redeploy, so compare against api/** and deploy/** changes, not master's tip)
gh run list --workflow api.yml -L 1 --json headSha,conclusion -q '.[0] | "deployed \(.headSha[0:7]) \(.conclusion)"'
git log -1 --format='last api change %h %s' -- api deploy/docker-compose.yml

# Live API and data
B=https://pinball-showcase.trmnlplugins.com
curl -s -o /dev/null -w "readyz %{http_code}\n" $B/readyz
curl -s $B/api/v1/dataset | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:d.get(k) for k in ("titles","showcase_titles","fetched_at","next_refresh","last_error")})'
curl -s "$B/api/v1/showcase?tz=America/New_York" | python3 -c 'import json,sys;d=json.load(sys.stdin);m=d["machine"];print("today:",m["name"],"|",m.get("edition_label"),"|",d["featured"]["pool_size"],"titles")'

# Self-hosted runner online? (jobs queue forever without it)
gh api repos/pythcon/trmnl-plugin-pinball-showcase/actions/runners -q '.runners[] | "\(.name) \(.status) busy=\(.busy)"'

# CI upload to TRMNL still switched on? (TRMNL_PUSH=true + TRMNL_API_KEY); last push job
gh variable list; gh secret list | cut -f1
gh run list --workflow plugin.yml -L 1 --json headSha,conclusion -q '.[0] | "plugin run \(.headSha[0:7]) \(.conclusion)"'
```

If the TRMNL MCP tools are connected, also check the plugin itself (skip quietly if they
answer "Tool not found"; the connector drops, so tell Todd to reconnect with `/mcp` only if
the task needs it):

- `AccountPluginSettingsTool getPluginSettingDetails {id: 497284}`: health and the
  instance's custom-field values (Todd's own; report them, don't reset them).
- `AccountPlaylistsTool listDevicePlaylist` for 56826 and 51325: the plugin is visible.

## Step 3: Report

Give Todd a short briefing, then ask what he wants to work on. Don't repeat the docs back.

```
## Session primed: Pinball Showcase

**Git:** <branch>, <clean / N uncommitted>, last commit <sha subject>
**Deploy:** API <sha> (<current / behind the last api change>), last run <ok/failed>
**Live:** readyz <code>, dataset <titles> titles fetched <time>, today: <machine>
**Runner:** <online/offline>   **TRMNL CI push:** <on/off>
**Plugin on trmnl.com:** <in sync / behind master since <sha> / unknown (MCP offline)>

**Next up (HANDOFF.md):**
1. ...
```

Only call out anything **wrong or new**: a failed run, `last_error` set, runner offline,
deploy behind master, plugin behind the repo.

## Standing rules

1. **Verify before saying done:** `make check` (API lint + tests, plugin lint + render
   tests), then look at `plugin/report/index.html` screenshots for every view you touched.
   trmnlp renders B/W/R/Y as grayscale; real colour previews come from the MCP
   `AccountMarkupTool startPreview` with `device_model: "og_bwry"`.
2. **New payload fields** must show up in `plugin/tests/fixtures` (`make fixtures`).
3. **Show Todd before building** visible changes to layouts or data presentation; he
   likes to see a proposal (mockup or analysis) first.
4. **Never print secrets** (`.env.production`, deploy key, TRMNL API key). Don't recreate
   or reprovision the server; deploys only update the one container.
5. **Commits:** push to `master` deploys production. Commit and push only when Todd asks or
   it's the agreed workflow for the task. End commit messages with the `Claude-Session`
   trailer the session provides.
6. **Plugin uploads are CI's job:** pushing `plugin/**` to master runs lint → test →
   `trmnlp push --force`; re-upload by hand with `gh workflow run plugin.yml --ref master`.
   Don't upload via MCP `importPluginSettingFiles`.
7. **Keep `HANDOFF.md` current:** tick off finished tasks and add new gotchas before ending
   a session that changed direction.
