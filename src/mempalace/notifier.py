"""Upstream version update notifier for MemPalace.

Checks GitHub Releases for newer versions of mempalace, throttled by a 24-hour
workspace-level cache, and alerts developers and agents via sys.stderr.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.request

GITHUB_REPO = "aruruka/mempalace"
DEFAULT_TTL_SECONDS = 86400  # 24 hours
DEFAULT_TIMEOUT_SECONDS = 1.5
BACKOFF_ON_ERROR_SECONDS = 3600  # 1 hour


def parse_semver(version_str: str) -> tuple[int, ...]:
    """Parse a semantic version string into an integer tuple for comparison.

    Strips any leading 'v' and trailing pre-release/build identifiers.

    Args:
        version_str: The version string, e.g. "v0.2.1", "0.3.0", "0.2.1-dev".

    Returns:
        A tuple of integers, e.g. (0, 2, 1).
    """
    clean = version_str.strip().lstrip("v")
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", clean)
    if not match:
        return (0, 0, 0)
    parts = [int(group) for group in match.groups() if group is not None]
    return tuple(parts)


class UpdateCache:
    """Manages the local workspace cache file for update notifications."""

    def __init__(self, workspace: Path) -> None:
        """Initialize with the workspace root directory.

        Args:
            workspace: The path to the workspace root.
        """
        self.workspace = workspace
        self.cache_file = workspace / "MemPalace" / ".cache.json"

    def read(self) -> dict[str, Any] | None:
        """Read cache data if file exists and contains valid JSON.

        Returns:
            The parsed cache dictionary, or None if missing or invalid.
        """
        if not self.cache_file.is_file():
            return None
        try:
            content = self.cache_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict) and "latest_version" in data and "last_checked_at" in data:
                return data
        except Exception:
            return None
        return None

    def write(self, latest_version: str, timestamp: float | None = None) -> None:
        """Write the latest version and check timestamp to the cache file.

        Args:
            latest_version: The version string detected upstream.
            timestamp: Epoch seconds for the check; defaults to time.time().
        """
        ts = timestamp if timestamp is not None else time.time()
        data = {
            "last_checked_at": ts,
            "latest_version": latest_version.lstrip("v"),
        }
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            # Ignore file system errors silently (e.g. read-only volume)
            pass

    def is_expired(self, cache: dict[str, Any] | None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
        """Check if the cache entry is absent or older than the TTL.

        Args:
            cache: Cache dictionary previously read, or None.
            ttl_seconds: Cache lifetime in seconds.

        Returns:
            True if absent or expired, False otherwise.
        """
        if cache is None:
            return True
        last_checked = cache.get("last_checked_at")
        if not isinstance(last_checked, (int, float)):
            return True
        return (time.time() - last_checked) > ttl_seconds


class GitHubVersionChecker:
    """Checks the public GitHub API for the latest release tag."""

    def __init__(self, repo: str = GITHUB_REPO) -> None:
        """Initialize with repository slug.

        Args:
            repo: GitHub repository slug in 'owner/repo' format.
        """
        self.repo = repo

    def fetch_latest_version(
        self, current_version: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> str | None:
        """Fetch the latest release tag name from GitHub Releases API.

        Fails completely silently on any network, timeout, or parsing error.

        Args:
            current_version: The currently installed version for the User-Agent header.
            timeout: Request timeout in seconds.

        Returns:
            Clean version string without 'v', or None on failure.
        """
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"mempalace/{current_version}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", None)
                if status is None:
                    status = getattr(resp, "code", None)
                if status == 200:
                    payload = json.loads(resp.read().decode("utf-8"))
                    tag_name = payload.get("tag_name")
                    if isinstance(tag_name, str):
                        return tag_name.strip().lstrip("v")
        except Exception:
            return None
        return None


class NoticeRenderer:
    """Renders the update notice banner."""

    @staticmethod
    def render_banner(current_version: str, latest_version: str, repo: str = GITHUB_REPO) -> str:
        """Format an actionable update banner.

        Args:
            current_version: Current version string.
            latest_version: Latest upstream version string.
            repo: GitHub repository slug.

        Returns:
            Formatted box string for display.
        """
        c_ver = current_version.lstrip("v")
        l_ver = latest_version.lstrip("v")
        lines = [
            "┌────────────────────────────────────────────────────────────────────────┐",
            f"│ mempalace update available: v{c_ver} -> v{l_ver}".ljust(73) + "│",
            "│ To update in your workspace:                                           │",
            f"│   uv add git+https://github.com/{repo}.git --tag v{l_ver}".ljust(73) + "│",
            "└────────────────────────────────────────────────────────────────────────┘",
        ]
        return "\n".join(lines)


def check_and_notify(
    workspace: Path,
    current_version: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """Check for an upstream update and return the banner string if available.

    Args:
        workspace: Path to workspace root.
        current_version: Current installed version string.
        ttl_seconds: Cache TTL in seconds.
        timeout: HTTP request timeout in seconds.

    Returns:
        The formatted banner string if an update is available, otherwise None.
    """
    if os.environ.get("MEMPALACE_NO_UPDATE_CHECK") == "1" or os.environ.get("CI") == "1":
        return None

    cache = UpdateCache(workspace)
    cached_data = cache.read()

    latest_ver: str | None = None

    if not cache.is_expired(cached_data, ttl_seconds=ttl_seconds):
        assert cached_data is not None
        latest_ver = cached_data.get("latest_version")
    else:
        # Cache is missing or expired: perform upstream check
        checker = GitHubVersionChecker()
        latest_ver = checker.fetch_latest_version(current_version=current_version, timeout=timeout)
        if latest_ver is not None:
            cache.write(latest_ver)
        else:
            # On network or API error, apply back-off so we don't retry on every command
            old_version = cached_data.get("latest_version") if cached_data else current_version
            cache.write(old_version, timestamp=time.time() - ttl_seconds + BACKOFF_ON_ERROR_SECONDS)
            latest_ver = cached_data.get("latest_version") if cached_data else None

    if latest_ver is not None:
        if parse_semver(latest_ver) > parse_semver(current_version):
            return NoticeRenderer.render_banner(current_version, latest_ver)

    return None


def maybe_emit_update_notice(workspace: Path, current_version: str) -> None:
    """Emit the update banner to sys.stderr if an update is available.

    Args:
        workspace: Path to workspace root.
        current_version: Current installed version string.
    """
    banner = check_and_notify(workspace, current_version)
    if banner:
        sys.stderr.write(banner + "\n")
        sys.stderr.flush()
