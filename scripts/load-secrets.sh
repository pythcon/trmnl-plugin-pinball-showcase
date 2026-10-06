#!/usr/bin/env bash
#
# Load .env.production into this repo's GitHub Actions secrets.
#
#   scripts/load-secrets.sh [.env.production]
#
#   DEPLOY_HOST / DEPLOY_USER / DEPLOY_PORT / DEPLOY_PATH  -> one secret each
#   DEPLOY_SSH_KEY_FILE   -> that private key's contents   -> DEPLOY_SSH_KEY
#   every other KEY=value -> one multi-line secret          -> ENV_PRODUCTION
#
# Values go to `gh` on stdin, never as arguments, so they don't show up in the
# process list or shell history. Re-run any time the file changes.
set -euo pipefail
cd "$(dirname "$0")/.."

FILE="${1:-.env.production}"
[ -f "$FILE" ] || { echo "No $FILE. Copy deploy/.env.production.example and fill it in." >&2; exit 1; }
command -v gh >/dev/null || { echo "Install the GitHub CLI (gh) first." >&2; exit 1; }

app_env=""
key_file=""
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|'#'*) continue ;; esac
  name="${line%%=*}"
  value="${line#*=}"
  case "$name" in
    DEPLOY_SSH_KEY_FILE) key_file="${value/#\~/$HOME}" ;;
    DEPLOY_*)
      printf '%s' "$value" | gh secret set "$name" >/dev/null
      echo "  set $name"
      ;;
    *) app_env+="$name=$value"$'\n' ;;
  esac
done < "$FILE"

[ -n "$key_file" ] || { echo "DEPLOY_SSH_KEY_FILE is not set in $FILE" >&2; exit 1; }
[ -f "$key_file" ] || { echo "Deploy key not found: $key_file" >&2; exit 1; }
gh secret set DEPLOY_SSH_KEY < "$key_file" >/dev/null
echo "  set DEPLOY_SSH_KEY (from $key_file)"

printf '%s' "$app_env" | gh secret set ENV_PRODUCTION >/dev/null
echo "  set ENV_PRODUCTION ($(printf '%s' "$app_env" | grep -c '=') variables)"
echo "Done. Secrets: $(gh secret list --json name -q '.[].name' | tr '\n' ' ')"
