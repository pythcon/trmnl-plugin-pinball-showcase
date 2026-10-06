# Deployment

The hosted API and website at **https://pinball-showcase.trmnlplugins.com** run on the
existing TRMNL plugins server, next to the other plugins. The server is pre-built and
permanent: deploys never provision or recreate it, they only update one container.
Self-hosters only need the root `compose.yaml` (see the main README).

## How a deploy works

```
push to master (api/**, deploy/docker-compose.yml)
  └─ GitHub Actions "API"
       ├─ test    ruff + pytest
       ├─ image   multi-arch build -> ghcr.io/pythcon/trmnl-plugin-pinball-showcase:{latest,<sha7>}
       └─ deploy  (self-hosted runner on the Mac Studio, everything from secrets)
            1. write deploy key to the runner's temp dir
            2. sync deploy/docker-compose.yml and .env (ENV_PRODUCTION + IMAGE_TAG=<sha7>)
            3. docker login ghcr.io, docker compose pull && up -d, prune old images
            4. health check from inside the server: curl 127.0.0.1:$PINBALL_HOST_PORT/readyz
            5. advisory public check of $PINBALL_PUBLIC_URL, then delete the key
```

- **Redeploy / roll back** without rebuilding: Actions -> API -> Run workflow, with
  `image_tag` set to an earlier 7-character SHA (or `latest`).
- **Pause deploys**: set the repository variable `DEPLOY_PROD=false`.
- The server's address, user, path and port live only in secrets, so they never appear
  in the workflow file or the (masked) logs.

## Runner

The server only accepts SSH from allow-listed addresses, so GitHub-hosted runners
(which connect from changing IPs) time out. The deploy job runs on this repo's
self-hosted runner instead:

- directory `~/Development/runners/pythcon/trmnl-plugin-pinball-showcase`
- name `trmnl-plugin-pinball-showcase-macstudio`, labels `self-hosted, trmnl-plugin-pinball-showcase`
- managed like the other runners: `runners status`, `runners start pinball-showcase`,
  auto-started at login by `StartRunners.app` (see `~/Development/runners/README.md`)

If the runner is offline the deploy job waits in the queue rather than failing; check
with `gh api repos/pythcon/trmnl-plugin-pinball-showcase/actions/runners`.

## Secrets

All secrets come from the git-ignored `.env.production` at the repo root
(template: `deploy/.env.production.example`):

```bash
scripts/load-secrets.sh          # re-run whenever .env.production changes
```

| Secret | From | Used for |
|---|---|---|
| `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PORT`, `DEPLOY_PATH` | `DEPLOY_*` lines | where to SSH and which directory holds the stack |
| `DEPLOY_SSH_KEY` | the file named by `DEPLOY_SSH_KEY_FILE` | the deploy key (ed25519, no passphrase, used only by CI) |
| `ENV_PRODUCTION` | every other line | written to `$DEPLOY_PATH/.env` on the server |

App settings in `ENV_PRODUCTION`: `PINBALL_HOST_PORT` (localhost port nginx proxies to),
`PINBALL_PUBLIC_URL` (used in QR codes), `PINBALL_REFRESH_TIME` +
`PINBALL_REFRESH_TIMEZONE` (daily OPDB download, midnight New York), and
`PINBALL_DEFAULT_TIMEZONE` (when the website's "Pinball of the Day" rolls over).

## Server layout (one-time setup, already done)

| Piece | Where |
|---|---|
| Stack | `$DEPLOY_PATH/docker-compose.yml` + `.env` (written by every deploy) |
| Data | Docker volume `pinball-data` (cached OPDB export, ETag, pick memo) |
| Container | `trmnl-plugin-pinball-showcase`, bound to `127.0.0.1:$PINBALL_HOST_PORT` only |
| TLS + proxy | host nginx, `/etc/nginx/conf.d/pinball-showcase.conf` (copy in `deploy/nginx/`) |
| Certificate | Let's Encrypt via certbot (webroot `/var/www/html`), renewed by `certbot.timer` |
| DNS | `pinball-showcase.trmnlplugins.com` proxied through Cloudflare |

The nginx config is installed by hand, not by the workflow, because the same nginx
serves the other plugins and a bad reload would take them down too. To change it:

```bash
scp deploy/nginx/pinball-showcase.conf root@<host>:/etc/nginx/conf.d/
ssh root@<host> 'nginx -t && systemctl reload nginx'
```

Recreating the setup on a new server:

```bash
mkdir -p $DEPLOY_PATH
# temporary HTTP-only vhost serving /.well-known from /var/www/html, then:
certbot certonly --webroot -w /var/www/html -d pinball-showcase.trmnlplugins.com
# install deploy/nginx/pinball-showcase.conf, nginx -t, reload
# add the deploy key's .pub to ~/.ssh/authorized_keys of DEPLOY_USER
```

## Operations

```bash
ssh root@<host>
cd $DEPLOY_PATH
docker compose ps
docker compose logs -f
curl -s 127.0.0.1:8082/api/v1/dataset   # export age, next refresh, last error
```

Point an uptime checker at `https://pinball-showcase.trmnlplugins.com/readyz`. If
`/api/v1/dataset` shows a `last_error` for more than a day, the daily OPDB download is
failing; the plugin keeps serving the last good export meanwhile.
