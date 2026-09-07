# pyright: basic
"""Unit tests for the upstream update notifier module."""

from __future__ import annotations

import json
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mempalace.notifier import (
    GitHubVersionChecker,
    NoticeRenderer,
    UpdateCache,
    check_and_notify,
    parse_semver,
)


def test_parse_semver_standard_and_prefixed() -> None:
    assert parse_semver("0.2.1") == (0, 2, 1)
    assert parse_semver("v0.3.0") == (0, 3, 0)
    assert parse_semver("1.10.4") == (1, 10, 4)
    assert parse_semver("0.2.1-dev") == (0, 2, 1)


def test_parse_semver_comparison() -> None:
    assert parse_semver("0.2.1") < parse_semver("0.3.0")
    assert parse_semver("0.2.1") < parse_semver("0.2.2")
    assert parse_semver("0.3.0") > parse_semver("0.2.9")
    assert not (parse_semver("0.2.1") < parse_semver("0.2.1"))


def test_update_cache_lifecycle(tmp_path: Path) -> None:
    workspace = tmp_path
    cache = UpdateCache(workspace)

    # Initially missing
    assert cache.read() is None
    assert cache.is_expired(None) is True

    # Write cache
    now = time.time()
    cache.write("0.3.0", timestamp=now)
    data = cache.read()
    assert data is not None
    assert data["latest_version"] == "0.3.0"
    assert data["last_checked_at"] == pytest.approx(now, abs=1.0)
    assert cache.is_expired(data, ttl_seconds=86400) is False

    # Expired check
    old_data = {"latest_version": "0.3.0", "last_checked_at": now - 90000}
    assert cache.is_expired(old_data, ttl_seconds=86400) is True


def test_update_cache_corrupted_json(tmp_path: Path) -> None:
    workspace = tmp_path
    cache_file = workspace / "MemPalace" / ".cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("invalid json content!", encoding="utf-8")

    cache = UpdateCache(workspace)
    assert cache.read() is None
    assert cache.is_expired(None) is True


def test_github_version_checker_success() -> None:
    checker = GitHubVersionChecker()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"tag_name": "v0.3.0"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        latest = checker.fetch_latest_version(current_version="0.2.1")
        assert latest == "0.3.0"


def test_github_version_checker_network_failure() -> None:
    checker = GitHubVersionChecker()
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Network unreachable"),
    ):
        latest = checker.fetch_latest_version(current_version="0.2.1")
        assert latest is None


def test_notice_renderer_contains_expected_tokens() -> None:
    banner = NoticeRenderer.render_banner(current_version="0.2.1", latest_version="0.3.0")
    assert "mempalace update available" in banner
    assert "v0.2.1 -> v0.3.0" in banner
    assert "uv add git+https://github.com/aruruka/mempalace.git --tag v0.3.0" in banner


def test_check_and_notify_disabled_by_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEMPALACE_NO_UPDATE_CHECK", "1")
    banner = check_and_notify(tmp_path, current_version="0.2.1")
    assert banner is None


def test_check_and_notify_with_fresh_cache_hit(tmp_path: Path) -> None:
    cache = UpdateCache(tmp_path)
    cache.write("0.3.0", timestamp=time.time())

    with patch.object(GitHubVersionChecker, "fetch_latest_version") as mock_fetch:
        banner = check_and_notify(tmp_path, current_version="0.2.1")
        assert banner is not None
        assert "v0.2.1 -> v0.3.0" in banner
        mock_fetch.assert_not_called()


def test_check_and_notify_up_to_date(tmp_path: Path) -> None:
    cache = UpdateCache(tmp_path)
    cache.write("0.2.1", timestamp=time.time())

    banner = check_and_notify(tmp_path, current_version="0.2.1")
    assert banner is None
