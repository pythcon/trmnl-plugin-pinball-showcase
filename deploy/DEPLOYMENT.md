# Deployment plan

How the hosted API at **`https://pinball.trmnlplugins.com`** gets built, shipped and run.
Self-hosters only need the root `compose.yaml` (see the main README).

## Pipeline

```
push to master ─▶ GitHub Actions "API" ─▶ ruff + pytest
                                      └─▶ multi-arch image ─▶ ghcr.io/pythcon/trmnl-plugin-pinball-showcase:{latest,<sha>,<semver>}
                                                         └─▶ (optional) SSH deploy job ─▶ server: docker compose pull && up -d ─▶ /readyz check

push to master ─▶ GitHub Actions "Plugin" ─▶ trmnlp lint + render tests (OG, OG 2-bit, X, portrait, B/W/R/Y)
                                         └─▶ (optional) trmnlp push ─▶ TRMNL private plugin / recipe
```

## Runtime

| Piece | Choice |
|---|---|
| Image | `ghcr.io/pythcon/trmnl-plugin-pinball-showcase` (amd64 + arm64), non-root, read-only rootfs |
| Process | uvicorn (single worker is plenty: responses are computed in ~2 ms from memory) |
| State | `/data` volume: cached `opdb-v2.json`, its ETag/Last-Modified, and `picks.json` (keeps today's pick stable across restarts) |
| Data refresh | In-process daily job at 07:00 UTC (after Match Play's ~06:30 rebuild), conditional GET, retries every 15 min on failure, keeps serving the last good export |
| Health | `GET /healthz` (liveness), `GET /readyz` (dataset loaded; 503 otherwise), `GET /api/v1/dataset` (age, next refresh, last error) |
| TLS / proxy | Caddy (`deploy/Caddyfile`, compose profile `caddy`) or the server's existing proxy → `127.0.0.1:8080` |
| Caching | `Cache-Control: public, max-age=300` on showcase responses |

## First-time setup

1. **DNS**: `pinball.trmnlplugins.com` → the server (A/AAAA, or CNAME/Cloudflare proxy like the other plugins).
2. **Server**:
   ```bash
   mkdir -p /opt/trmnl-pinball && cd /opt/trmnl-pinball
   # copy deploy/docker-compose.yml, deploy/Caddyfile, deploy/.env.example -> .env
   docker compose pull && docker compose up -d                 # API only (existing proxy)
   docker compose --profile caddy up -d                         # or API + Caddy
   curl -fsS http://127.0.0.1:8080/readyz
   ```
3. **GHCR**: after the first image push, make the package public (GitHub → Packages →
   trmnl-plugin-pinball-showcase → Package settings → Change visibility) so the server and
   self-hosters can pull without credentials.
4. **Smoke test**: `curl -s https://pinball.trmnlplugins.com/api/v1/showcase | jq .machine.name`
5. **TRMNL**: `cd plugin && bin/trmnlp login && bin/trmnlp push`, then add the `id:` it
   reports to `plugin/src/settings.yml` and commit, so later pushes update the same plugin.

## Continuous deployment (optional, off by default)

The `deploy` job in `.github/workflows/api.yml` runs only when the repository variable
`DEPLOY_ENABLED` is `true`. It needs a `production` environment with these secrets:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | server hostname/IP |
| `DEPLOY_USER` | SSH user with Docker access |
| `DEPLOY_SSH_KEY` | private key (deploy-only key recommended) |
| `DEPLOY_PORT` | optional, default 22 |
| `DEPLOY_PATH` | e.g. `/opt/trmnl-pinball` |

Alternative without inbound SSH: run Watchtower (or a systemd timer doing
`docker compose pull && docker compose up -d`) on the server, scoped to this container.

Plugin publishing works the same way: set `TRMNL_PUSH=true` and the `TRMNL_API_KEY` secret.

## Releases and rollback

- Every master build is tagged with its commit SHA; `git tag vX.Y.Z && git push --tags`
  also publishes `X.Y.Z` and `X.Y`.
- Roll back by setting `PINBALL_IMAGE_TAG=<sha or version>` in the server's `.env` and
  `docker compose up -d`.

## Monitoring

- Point an uptime checker (Uptime Kuma, Healthchecks, UptimeRobot...) at
  `https://pinball.trmnlplugins.com/readyz`.
- Alert if `/api/v1/dataset` shows `last_error` for more than a day or `fetched_at` older
  than ~30 hours: the plugin keeps working on yesterday's data, but it should be looked at.

## Open items (to settle together)

- [ ] Which server/host runs it, and whether it reuses the proxy in front of grafana.trmnlplugins.com.
- [ ] Cloudflare in front (caching + rate limiting) or direct.
- [ ] SSH deploy job vs. pull-based (Watchtower/timer) updates.
- [ ] Uptime monitoring target and alert channel.
- [ ] Publish as a public TRMNL recipe once it has run privately for a while.
