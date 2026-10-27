#!/usr/bin/env bash
# Checks the hosted compose's proxy trust (D-032) with its real nginx configuration: visitor addresses sent by the
# tunnel's address (10.213.0.2) get their own rate-limit buckets, IPv6 included, and the same header from any other
# peer is ignored. Runs web from hosting/oracle/compose.yaml with a stub API: no cloudflared, Aura or secret.
# Uses the image in WEB_IMAGE, or the local one compose_smoke.sh builds.
set -euo pipefail
cd "$(dirname "$0")/.."

export COMPOSE_PROJECT_NAME=medical-chatbot-hosted-check
export API_IMAGE="${API_IMAGE:-medical-chatbot-api:local}" WEB_IMAGE="${WEB_IMAGE:-medical-chatbot-web:local}"
# Placeholders: Compose requires them, but no API, Aura or tunnel runs here.
export WEB_PORT="${WEB_PORT:-18081}" NEO4J_URI=neo4j://127.0.0.1:1 NEO4J_PASSWORD=unused PUBLIC_ORIGIN=https://example.test TUNNEL_TOKEN=unused OLLAMA_API_KEY=unused
BUSYBOX=busybox:1.37@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e
compose() { docker compose --env-file /dev/null -f hosting/oracle/compose.yaml "$@"; }
fail() { echo "HOSTED CHECK FAIL: $*" >&2; exit 1; }
# A stub answers for the API at once, so only nginx's limits decide the status codes.
compose up --no-start --no-build --no-deps web >/dev/null
docker run -d --name "$COMPOSE_PROJECT_NAME-stub" --network "${COMPOSE_PROJECT_NAME}_default" --network-alias api "$BUSYBOX" \
  sh -c 'mkdir -p /www && echo ok > /www/index.html && httpd -f -p 5000 -h /www' >/dev/null
trap 'docker rm -f "$COMPOSE_PROJECT_NAME-stub" >/dev/null 2>&1 || true; compose down -v --remove-orphans >/dev/null 2>&1 || true' EXIT
compose up -d --no-build --no-deps web >/dev/null 2>&1
compose exec -T web nginx -t -q || fail "nginx configuration test"
compose exec -T web sh -c 'cat /etc/nginx/realip.d/tunnel.conf' | grep -q 'set_real_ip_from 10.213.0.2;' || fail "trust file missing"

# statuses <peer address> <header values...>: one request per value, 6 at a time, from a client at that address.
statuses() {
  local ip=$1; shift
  docker run --rm --network "${COMPOSE_PROJECT_NAME}_edge" --ip "$ip" "$BUSYBOX" sh -c '
    for v in "$@"; do
      wget -q -S -O /dev/null --header "CF-Connecting-IP: $v" "http://web:8080/api/?search=what+causes+asthma" 2>&1 \
        | awk "/HTTP\\//{print \$2}" &
      [ $(( $(jobs -p | wc -l) )) -ge 6 ] && wait
    done; wait' sh "$@"
}
for _ in $(seq 1 30); do compose exec -T web sh -c 'wget -q -O /dev/null http://127.0.0.1:8080/' 2>/dev/null && break; sleep 1; done

distinct=$(seq 1 50 | sed 's/^/198.51.100./')
distinct6=$(seq 1 50 | sed 's/^/2001:db8::/')
same=$(for _ in $(seq 1 50); do echo 203.0.113.7; done)

limited() { grep -c '^429$' || true; }
[ "$(statuses 10.213.0.2 $distinct | limited)" = 0 ] || fail "tunnel visitors with different addresses shared a bucket"
[ "$(statuses 10.213.0.2 $distinct6 | limited)" = 0 ] || fail "IPv6 visitor addresses were not trusted"
[ "$(statuses 10.213.0.2 $same | limited)" -gt 0 ] || fail "one tunnel visitor was not rate-limited"
[ "$(statuses 10.213.0.5 $distinct | limited)" -gt 0 ] || fail "an untrusted peer's header was trusted"

echo "Hosted check passed"
