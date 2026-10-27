"""Static checks on the hosted stack's compose file (D-032); scripts/hosted_check.sh exercises it with Docker."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTED = (ROOT / "hosting" / "oracle" / "compose.yaml").read_text(encoding="utf-8")


def service(name):
    """The text of one service block."""
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \S|^\S)", HOSTED, flags=re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(1)


def test_no_application_port_is_public():
    ports = re.findall(r'^\s+- "([^"]+)"$', HOSTED, flags=re.MULTILINE)
    assert ports == ["127.0.0.1:${WEB_PORT:-8080}:8080"]
    assert "network_mode" not in HOSTED and "neo4j:" not in HOSTED


def test_the_language_model_is_off_and_cannot_be_switched_on_from_env():
    assert 'LLM_UNDERSTANDING: "off"' in HOSTED and "${LLM_UNDERSTANDING" not in HOSTED


def test_only_the_tunnel_is_trusted_for_visitor_addresses():
    assert re.findall(r"set_real_ip_from (\S+);", HOSTED) == ["10.213.0.2"]
    assert "ipv4_address: 10.213.0.2" in service("cloudflared")
    # Fixed addresses, and automatic ones from a range that excludes them, so no other container can take .2.
    assert "ipv4_address: 10.213.0.3" in service("web") and "ip_range: 10.213.0.4/30" in HOSTED


def test_the_tunnel_keeps_no_logs_and_reads_its_token_from_env():
    cloudflared = service("cloudflared")
    assert "driver: none" in cloudflared
    assert "TUNNEL_TOKEN: ${TUNNEL_TOKEN:?" in cloudflared and "--token" not in cloudflared
    assert re.search(r"cloudflare/cloudflared:[\d.]+@sha256:[0-9a-f]{64}", cloudflared)


def test_secrets_and_the_origin_come_from_env_and_every_service_is_bounded():
    for variable in ("NEO4J_URI", "NEO4J_PASSWORD", "PUBLIC_ORIGIN", "API_IMAGE", "WEB_IMAGE"):
        assert f"${{{variable}:?" in HOSTED, variable
    for name in ("importer", "api", "web", "cloudflared"):
        assert re.search(r"mem_limit: \d+m", service(name)), name


def test_the_hosted_compose_is_released_and_counts_as_shipped():
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "cp hosting/oracle/compose.yaml dist/compose.hosted.yaml" in release
    assert "bash scripts/hosted_check.sh" in release
    assert '"hosting/oracle/compose.yaml"' in (ROOT / "scripts" / "next_release.py").read_text(encoding="utf-8")
