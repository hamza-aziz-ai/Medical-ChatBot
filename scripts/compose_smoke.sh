#!/usr/bin/env bash
# Disposable end-to-end check of the Compose stack: init, static page, answer through the /api
# proxy, abstention, rate limiting, API outage, graph readiness, and no question in any log.
# Uses its own project name and throwaway secrets, and deletes its containers and volumes on exit.
# Set SKIP_BUILD=1 with API_IMAGE and WEB_IMAGE to test images that are already built.
set -euo pipefail
cd "$(dirname "$0")/.."

export COMPOSE_PROJECT_NAME=medical-chatbot-smoke
export NEO4J_PASSWORD="smoke-$RANDOM$RANDOM$RANDOM"
export WEB_PORT="${WEB_PORT:-18080}"
export LOG_LEVEL=DEBUG
export LLM_UNDERSTANDING=off  # the smoke test never reaches a language model (D-027)
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
missing=$(curl -s -w '\n%{http_code}' "$BASE/no-such-page")
[ "$(tail -n1 <<<"$missing")" = 404 ] && grep -q 'Page not found' <<<"$missing" || fail "404 page"

reply=$(ask what are the symptoms of asthma "$SENTINEL")
[ "$(tail -n1 <<<"$reply")" = 200 ] || fail "graph answer status"
grep -q 'breathing difficulty' <<<"$reply" || fail "graph answer content"

grep -Eq '"status": *"abstain"' <<<"$(ask how long does asthma last "$SENTINEL")" || fail "abstention"

# 60 parallel requests exceed nginx's 10/s rate with a burst of 20, so some must get 429.
codes=$(seq 1 60 | xargs -P 30 -I{} curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/?search=what+causes+asthma")
grep -q '^429$' <<<"$codes" || fail "rate limiting did not engage"
# D-029: answers, health and nginx's own 429 are no-store; the static page keeps only its security headers.
header() { curl -s -D - -o /dev/null "$1" | tr -d '\r' | awk -v h="$2" 'tolower($0) ~ "^" tolower(h) ":" && !n++'; }
limited=$(seq 1 60 | xargs -P 30 -I{} curl -s -D - -o /dev/null "$BASE/api/?search=what+causes+asthma" | tr -d '\r' | awk '/^HTTP/{s=$2} tolower($0) ~ /^cache-control: no-store/ && s==429 {found=1} END{if (found) print "ok"}')
[ "$limited" = ok ] || fail "a 429 from nginx is not no-store"
sleep 3
[ "$(header "$BASE/api/?search=what+causes+asthma" Cache-Control)" = "Cache-Control: no-store" ] || fail "answer not no-store"
[ "$(header "$BASE/api/health" Cache-Control)" = "Cache-Control: no-store" ] || fail "health not no-store"
header "$BASE/api/health" X-Content-Type-Options | grep -qi nosniff || fail "security headers lost on /api/"
[ -z "$(header "$BASE/" Cache-Control)" ] || fail "the static page's caching changed"
header "$BASE/" Content-Security-Policy | grep -q "default-src 'self'" || fail "static page lost its CSP"
sleep 3

compose stop api >/dev/null
status=$(ask what causes asthma "$SENTINEL" | tail -n1)
case "$status" in 502|504) ;; *) fail "outage returned $status, expected 502 or 504" ;; esac
compose start api >/dev/null
compose up -d --wait api >/dev/null

# Readiness (D-022): ok with the imported graph, 503 while Neo4j is down and the API keeps running, ok again after.
health() { curl -s -o /dev/null -w '%{http_code}' "$BASE/api/health"; }
[ "$(health)" = 200 ] || fail "readiness with the imported graph"
compose stop neo4j >/dev/null
[ "$(health)" = 503 ] || fail "readiness during a graph outage, expected 503"
[ "$(ask what causes asthma "$SENTINEL" | tail -n1)" = 503 ] || fail "a question during a graph outage, expected 503"
compose up -d --wait neo4j >/dev/null
for _ in $(seq 1 30); do [ "$(health)" = 200 ] && break; sleep 2; done
[ "$(health)" = 200 ] || fail "readiness did not recover after the graph came back"

# BUG-003: a question whose worker the watchdog kills must not be logged. The API is pointed at a listener that
# accepts and never answers, so the request stalls until Gunicorn's timeout (shortened to 3 s here) kills the worker.
stall_net="$COMPOSE_PROJECT_NAME-stall"
cleanup_stall() { docker rm -f "$stall_net-api" "$stall_net-db" >/dev/null 2>&1 || true; docker network rm "$stall_net" >/dev/null 2>&1 || true; }
trap 'cleanup_stall; compose --profile init down -v --remove-orphans >/dev/null 2>&1 || true' EXIT
docker network create "$stall_net" >/dev/null
docker run -d --name "$stall_net-db" --network "$stall_net" --network-alias stall   busybox:1.37@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e   sh -c 'while true; do sleep 3600 | nc -l -p 7687 >/dev/null; done' >/dev/null
docker run -d --name "$stall_net-api" --network "$stall_net" --no-healthcheck -e NEO4J_URI=neo4j://stall:7687   -e NEO4J_PASSWORD=unused -e LLM_UNDERSTANDING=off -e GUNICORN_CMD_ARGS="--timeout 3"   "${API_IMAGE:-medical-chatbot-api:local}" >/dev/null
sleep 4
docker exec "$stall_net-api" python -c "import urllib.request
try: urllib.request.urlopen('http://127.0.0.1:5000/?search=what+causes+asthma+$SENTINEL', timeout=30)
except Exception: pass"
sleep 2
stalled=$(docker logs "$stall_net-api" 2>&1; docker exec "$stall_net-api" sh -c 'cat /app/logs/*/*/*.log')
grep -q 'WORKER TIMEOUT' <<<"$stalled" || fail "the stalled request did not reach Gunicorn's timeout"
if grep -q "$SENTINEL" <<<"$stalled"; then fail "a question reached the logs when a worker timed out"; fi
cleanup_stall

logs=$(compose logs --no-color; compose exec -T api sh -c 'cat /app/logs/*/*/*.log')
[ -n "$logs" ] || fail "no logs collected"
if grep -q "$SENTINEL" <<<"$logs"; then fail "a question reached the logs"; fi

echo "Compose smoke test passed"
