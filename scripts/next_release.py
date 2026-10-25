"""Decide whether main needs a release, and which version it gets (D-019).

Run by .github/workflows/autorelease.yml. Prints `release=true|false`, `tag` and `sha` lines for
$GITHUB_OUTPUT, or exits non-zero with recovery steps when the last release is incomplete or a lookup failed.

State-based on purpose: it releases origin/main HEAD when its shipped files differ from the last
published release, so duplicate, replaced or no-op runs are harmless. Several merges can share a release.
"""
import argparse
import fnmatch
import json
import re
import subprocess
import sys

VERSION_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
BUMPS = ("patch", "minor", "major")

# Files copied into the images or attached to the release. Docs, eval, tests and workflows only trigger checks.
SHIPPED = ["docker/*", "compose.yaml", "requirements.txt", "requirements-deploy.txt", ".env.example", "api/*", "frontend/*"]
NOT_SHIPPED = ["api/models/*", "api/data/questions.json", "frontend/tests/*", "frontend/README.md"]

# Lookup results. "error" is never read as absence: a failed lookup stops the run.
PRESENT, ABSENT, ERROR = "present", "absent", "error"


class Stop(Exception):
    """The run must stop without releasing; the message says what the owner should do."""


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def version(tag):
    return tuple(int(part) for part in VERSION_TAG.match(tag).groups())


def bump(tag, level):
    major, minor, patch = version(tag)
    return {"major": f"v{major + 1}.0.0", "minor": f"v{major}.{minor + 1}.0", "patch": f"v{major}.{minor}.{patch + 1}"}[level]


def is_shipped(path):
    return any(fnmatch.fnmatch(path, p) for p in SHIPPED) and not any(fnmatch.fnmatch(path, p) for p in NOT_SHIPPED)


def tags_on(ref):
    """Stable version tags reachable from ref, newest first."""
    return sorted((t for t in git("tag", "--merged", ref).split() if VERSION_TAG.match(t)), key=version, reverse=True)


def shipped_changes(base, head):
    return [path for path in git("diff", "--name-only", base, head).split() if is_shipped(path)]


def release_state(tag, releases):
    """published, draft or absent, from the full release list (drafts are only listed, never found by tag)."""
    matches = [release for release in releases if release["tag_name"] == tag]
    if not matches:
        return ABSENT
    return "draft" if any(release["draft"] for release in matches) else "published"


def plan(head, tags, releases, image_state, bump_level, changes, all_tags=()):
    """The release to make, as (tag, sha), or None. Raises Stop when a human must act first.

    tags: version tags on main, newest first. releases: every release (None if the listing failed).
    image_state(version) -> present, absent or error. changes(base_tag) -> shipped paths changed since it.
    """
    if not tags:
        raise Stop("No vX.Y.Z tag on main; cut the first release by hand.")
    if releases is None:
        raise Stop("Could not list releases; nothing was changed. Re-run later.")

    baseline = None
    for tag in tags:
        state = release_state(tag, releases)
        if state == "published":
            baseline = tag
            break
        if state == "draft":
            raise Stop(f"{tag} has a draft release, so its publication is incomplete. If the draft's manifest.json "
                       f"matches the tag's commit and the tested digests, finish it by hand (see docs/ROLLBACK.md); "
                       f"otherwise delete the draft.")
        images = image_state(tag[1:])
        if images == ERROR:
            raise Stop(f"Could not check the images of {tag}; nothing was changed. Re-run later.")
        if images == PRESENT:
            raise Stop(f"{tag} has version images but no release. Leave both untouched and publish the next unused "
                       f"version by hand through release.yml with tag and sha (see docs/ROLLBACK.md).")
        # No release and no images: an unused, abandoned tag. It stays reserved; keep looking for the baseline.
    if baseline is None:
        raise Stop("No published release on main to compare with; cut one by hand.")

    if not changes(baseline):
        return None
    tag = bump(tags[0], bump_level)
    if tag in all_tags:
        raise Stop(f"{tag} already exists outside main; choose the next version by hand.")
    return tag, head


def image_lookup(prefix):
    def image_state(number):
        for image in ("api", "web"):
            result = subprocess.run(["docker", "buildx", "imagetools", "inspect", f"{prefix}-{image}:{number}"],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                return PRESENT
            if not re.search(r"\bnot found\b", result.stderr, re.IGNORECASE):
                return ERROR
        return ABSENT
    return image_state


def list_releases(repo):
    result = subprocess.run(["gh", "api", "--paginate", f"repos/{repo}/releases", "--jq", ".[] | {tag_name, draft}"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def label_bump(repo, base, head):
    """The highest release:minor / release:major label on the pull requests merged in base..head, else patch."""
    level = "patch"
    for sha in git("rev-list", "--first-parent", "--merges", f"{base}..{head}").split():
        result = subprocess.run(["gh", "api", f"repos/{repo}/commits/{sha}/pulls", "--jq", ".[].labels[].name"],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise Stop("Could not read pull request labels; nothing was changed. Re-run later.")
        for label in result.stdout.split():
            if label.startswith("release:") and label[8:] in BUMPS and BUMPS.index(label[8:]) > BUMPS.index(level):
                level = label[8:]
    return level


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--image-prefix", required=True)
    parser.add_argument("--bump", choices=("auto", *BUMPS), default="auto")
    parser.add_argument("--ref", default="origin/main")
    args = parser.parse_args(argv)

    head = git("rev-parse", args.ref).strip()
    tags = tags_on(args.ref)
    releases = list_releases(args.repo)
    try:
        published = next((t for t in tags if release_state(t, releases or []) == "published"), None)
        level = args.bump if args.bump != "auto" else (label_bump(args.repo, published, head) if published else "patch")
        result = plan(head, tags, releases, image_lookup(args.image_prefix), level,
                      lambda base: shipped_changes(base, head), set(git("tag", "-l").split()))
    except Stop as stop:
        print(f"::error::{stop}", file=sys.stderr)
        return 1
    if result is None:
        print("release=false")
        print("Nothing shipped has changed since the last release.", file=sys.stderr)
        return 0
    tag, sha = result
    print("release=true")
    print(f"tag={tag}")
    print(f"sha={sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
