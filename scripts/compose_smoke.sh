#!/usr/bin/env bash
# Disposable end-to-end check of the Compose stack: init, static page, answer through the /api
# proxy, abstention, rate limiting, API outage, and no question in any log.
# Uses its own project name and throwaway secrets, and deletes its containers and volumes on exit.
# Set SKIP_BUILD=1 with API_IMAGE and WEB_IMAGE to test images that are already built.
set -euo pipefail
cd "$(dirname "$0")/.."

export COMPOSE_PROJECT_NAME=medical-chatbot-smoke
export NEO4J_PASSWORD="smoke-$RANDOM$RANDOM$RANDOM"
export WEB_PORT="${WEB_PORT:-18080}"
export LOG_LEVEL=DEBUG
SENTINEL="sentinelq$RANDOM$RANDOM"
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

ask() {  # ask <question words...>; prints the body, then the status on the last line
  local query; query=$(IFS=+; echo "$*")
  curl -s -w '\n%{http_code}' "$BASE/api/?search=$query"
}

for _ in $(seq 1 30); do curl -fs -o /dev/null "$BASE/" && break; sleep 1; done
curl -fs "$BASE/" | grep -q '<div id="app">' || fail "static page"

reply=$(ask what are the symptoms of asthma "$SENTINEL")
[ "$(tail -n1 <<<"$reply")" = 200 ] || fail "graph answer status"
grep -q 'breathing difficulty' <<<"$reply" || fail "graph answer content"

grep -Eq '"status": *"abstain"' <<<"$(ask how long does asthma last "$SENTINEL")" || fail "abstention"

# 60 parallel requests exceed nginx's 10/s rate with a burst of 20, so some must get 429.
codes=$(seq 1 60 | xargs -P 30 -I{} curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/?search=what+causes+asthma")
grep -q '^429$' <<<"$codes" || fail "rate limiting did not engage"
sleep 3

compose stop api >/dev/null
status=$(ask what causes asthma "$SENTINEL" | tail -n1)
case "$status" in 502|504) ;; *) fail "outage returned $status, expected 502 or 504" ;; esac
compose start api >/dev/null
compose up -d --wait api >/dev/null

logs=$(compose logs --no-color; compose exec -T api sh -c 'cat /app/logs/*/*/*.log')
[ -n "$logs" ] || fail "no logs collected"
if grep -q "$SENTINEL" <<<"$logs"; then fail "a question reached the logs"; fi

echo "Compose smoke test passed"
