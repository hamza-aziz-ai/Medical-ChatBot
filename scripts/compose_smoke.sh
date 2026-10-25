#!/usr/bin/env bash
# Disposable end-to-end check of the Compose stack: init, static page, authenticated answer through
# the /api proxy, wrong token, abstention, API outage, and no question or token in any log.
# Uses its own project name and throwaway secrets, and deletes its containers and volumes on exit.
# Set SKIP_BUILD=1 with API_IMAGE and WEB_IMAGE to test images that are already built.
set -euo pipefail
cd "$(dirname "$0")/.."

export COMPOSE_PROJECT_NAME=medical-chatbot-smoke
export NEO4J_PASSWORD="smoke-$RANDOM$RANDOM$RANDOM"
export CHATBOT_API_TOKEN="smoketoken$RANDOM$RANDOM$RANDOM"
export WEB_PORT="${WEB_PORT:-18080}"
export LOG_LEVEL=DEBUG
SENTINEL="sentinelq$RANDOM$RANDOM"
WRONG_TOKEN="wrongtoken$RANDOM$RANDOM"
BASE="http://127.0.0.1:$WEB_PORT"
# An explicit empty env file keeps a developer's real .env out of the test.
compose() { docker compose --env-file /dev/null "$@"; }
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

trap 'compose --profile init down -v --remove-orphans >/dev/null 2>&1 || true' EXIT

if [ "${SKIP_BUILD:-0}" = "1" ]; then
  # Pull explicitly so Compose never falls back to building a different image.
  docker pull -q "${API_IMAGE:?}" >/dev/null && docker pull -q "${WEB_IMAGE:?}" >/dev/null
else
  compose --profile init build
fi
compose up -d --wait neo4j
compose --profile init run --rm importer >/dev/null
compose up -d --wait api web
compose exec -T web nginx -t -q || fail "nginx configuration test"

ask() {  # ask <token> <question words...>; prints "<status> <body>"
  local token=$1; shift
  local query; query=$(IFS=+; echo "$*")
  curl -s -w '\n%{http_code}' -H "Authorization: Bearer $token" "$BASE/api/?search=$query"
}

for _ in $(seq 1 30); do curl -fs -o /dev/null "$BASE/" && break; sleep 1; done
curl -fs "$BASE/" | grep -q '<div id="app">' || fail "static page"

reply=$(ask "$CHATBOT_API_TOKEN" what are the symptoms of asthma "$SENTINEL")
[ "$(tail -n1 <<<"$reply")" = 200 ] || fail "graph answer status"
grep -q 'breathing difficulty' <<<"$reply" || fail "graph answer content"

[ "$(ask "$WRONG_TOKEN" what causes asthma "$SENTINEL" | tail -n1)" = 401 ] || fail "wrong token not rejected"

grep -q 'I cannot answer' <<<"$(ask "$CHATBOT_API_TOKEN" how long does asthma last "$SENTINEL")" || fail "abstention"

compose stop api >/dev/null
status=$(ask "$CHATBOT_API_TOKEN" what causes asthma "$SENTINEL" | tail -n1)
case "$status" in 502|504) ;; *) fail "outage returned $status, expected 502 or 504" ;; esac
compose start api >/dev/null
compose up -d --wait api >/dev/null

logs=$(compose logs --no-color; compose exec -T api sh -c 'cat /app/logs/*/*/*.log')
[ -n "$logs" ] || fail "no logs collected"
for secret in "$SENTINEL" "$CHATBOT_API_TOKEN" "$WRONG_TOKEN"; do
  if grep -q "$secret" <<<"$logs"; then fail "a question or token reached the logs"; fi
done

echo "Compose smoke test passed"
