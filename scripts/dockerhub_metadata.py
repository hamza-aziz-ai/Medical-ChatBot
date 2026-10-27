"""Make the Docker Hub repositories show what docs/dockerhub/ says (D-031).

    python scripts/dockerhub_metadata.py           # run by .github/workflows/dockerhub-metadata.yml after every merge
    python scripts/dockerhub_metadata.py --check   # validate the files only; no network

Sets each repository's short description and overview and turns on immutable version tags. A repository that already
matches is left alone, and every change is read back. Categories have no API and are set by hand.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "docs" / "dockerhub" / "repositories.json"
HUB = "https://hub.docker.com"
MAX_DESCRIPTION, MAX_OVERVIEW = 100, 25000  # bytes; Docker Hub's limits


class HubError(Exception):
    """A Docker Hub request failed or did not take effect; the message never holds a credential."""


def desired(config_path=CONFIG):
    """{repository: wanted settings}, refusing anything Docker Hub would truncate or reject."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    # Stripped on both sides, in case Docker Hub trims surrounding whitespace.
    overview = (config_path.parent / config["overview"]).read_text(encoding="utf-8").strip()
    rules = config["immutable_tags_rules"]
    if len(overview.encode()) > MAX_OVERVIEW:
        raise HubError(f"the overview is over {MAX_OVERVIEW} bytes")
    if not rules or not all(isinstance(rule, str) and rule for rule in rules):
        raise HubError("immutable_tags_rules must list at least one pattern")
    wanted = {}
    for repository, description in config["repositories"].items():
        if not description or len(description.encode()) > MAX_DESCRIPTION:
            raise HubError(f"{repository}'s description must be 1 to {MAX_DESCRIPTION} bytes")
        wanted[repository] = {"description": description, "full_description": overview,
                              "immutable_tags_settings": {"enabled": True, "rules": rules}}
    return wanted


def differences(current, wanted):
    """Which of 'overview' and 'immutable' must change for current (a repository GET) to match wanted."""
    changes = set()
    if current.get("description") != wanted["description"] or (current.get("full_description") or "").strip() != wanted["full_description"]:
        changes.add("overview")
    if current.get("immutable_tags_settings") != wanted["immutable_tags_settings"]:
        changes.add("immutable")
    return changes


def request(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(HUB + path, data, headers, method=method), timeout=30) as reply:
            return json.loads(reply.read() or b"{}")
    except urllib.error.HTTPError as error:
        raise HubError(f"{method} {path} answered {error.code}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise HubError(f"{method} {path} failed: {error.__class__.__name__}") from None


def login(username, secret):
    token = request("POST", "/v2/auth/token", {"identifier": username, "secret": secret}).get("access_token")
    if not token:
        raise HubError("Docker Hub returned no access token")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{token}")
    return token


def sync(namespace, wanted, token, call=request, log=print):
    for repository, want in sorted(wanted.items()):
        path = f"/v2/namespaces/{namespace}/repositories/{repository}"
        changes = differences(call("GET", path, token=token), want)
        if not changes:
            log(f"{namespace}/{repository} already matches")
            continue
        if "overview" in changes:
            # Docker Hub documents no namespace-scoped route for this; the repository route still takes it.
            call("PATCH", f"/v2/repositories/{namespace}/{repository}",
                 {"description": want["description"], "full_description": want["full_description"]}, token)
        if "immutable" in changes:
            settings = want["immutable_tags_settings"]
            call("PATCH", f"{path}/immutabletags",
                 {"immutable_tags": settings["enabled"], "immutable_tags_rules": settings["rules"]}, token)
        left = differences(call("GET", path, token=token), want)
        if left:
            raise HubError(f"{namespace}/{repository} still differs after updating: {', '.join(sorted(left))}")
        log(f"{namespace}/{repository} updated: {', '.join(sorted(changes))}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        wanted = desired()
        if argv == ["--check"]:
            print(f"{len(wanted)} repositories valid")
            return 0
        namespace, secret = os.environ.get("DOCKERHUB_USERNAME", ""), os.environ.get("DOCKERHUB_TOKEN", "")
        if not namespace or not secret:
            print("Docker Hub metadata is not configured: set DOCKERHUB_USERNAME and DOCKERHUB_TOKEN", file=sys.stderr)
            return 1
        sync(namespace, wanted, login(namespace, secret))
    except (OSError, ValueError, KeyError, HubError) as error:
        print(f"Docker Hub metadata failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
