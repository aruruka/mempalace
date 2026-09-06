# pyright: basic
"""Unit and functional tests for the workspace initializer module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mempalace import retrieval, storage
from mempalace.cli import app
from mempalace.initializer import (
    AgentFlavor,
    WorkspaceInitializerConfig,
    generate_kickoff_prompt,
    initialize_workspace,
    parse_agent_flavor,
)


def test_parse_agent_flavor_valid() -> None:
    assert parse_agent_flavor(None) == AgentFlavor.GENERIC
    assert parse_agent_flavor("") == AgentFlavor.GENERIC
    assert parse_agent_flavor("antigravity") == AgentFlavor.ANTIGRAVITY
    assert parse_agent_flavor("gemini-cli") == AgentFlavor.ANTIGRAVITY
    assert parse_agent_flavor("claude") == AgentFlavor.CLAUDE
    assert parse_agent_flavor("opencode") == AgentFlavor.OPENCODE
    assert parse_agent_flavor("hermes") == AgentFlavor.HERMES
    assert parse_agent_flavor("cursor") == AgentFlavor.CURSOR
    assert parse_agent_flavor("generic") == AgentFlavor.GENERIC


def test_parse_agent_flavor_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown agent flavor 'invalid_xyz'"):
        parse_agent_flavor("invalid_xyz")


def test_generate_kickoff_prompt() -> None:
    prompt = generate_kickoff_prompt(AgentFlavor.ANTIGRAVITY, Path("/dummy/my-project"))
    assert "my-project" in prompt
    assert "memory-sync" in prompt
    assert "mempalace doctor" in prompt
    assert "setup-mempalace" in prompt
    assert 'mempalace search --mode bm25 "welcome"' in prompt


def test_initialize_workspace_scaffolding(tmp_path: Path) -> None:
    cfg = WorkspaceInitializerConfig(
        workspace=tmp_path,
        agent_flavor=AgentFlavor.ANTIGRAVITY,
        seed_essences=True,
        install_skills=True,
        setup_decisions=True,
        setup_scripts=True,
        kickoff_file="MEMPALACE_KICKOFF.md",
    )
    report = initialize_workspace(cfg)

    assert report.db_initialized
    assert report.docs_indexed >= 1
    assert (tmp_path / "MemPalace" / "essences" / "README.md").exists()
    assert (tmp_path / "docs" / "decisions" / "README.md").exists()
    assert (tmp_path / "docs" / "decisions" / "template.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".agents" / "skills" / "memory-sync" / "SKILL.md").exists()
    assert (tmp_path / "scripts" / "setup-mempalace.ps1").exists()
    assert (tmp_path / "scripts" / "setup-mempalace.sh").exists()
    assert (tmp_path / "MEMPALACE_KICKOFF.md").exists()

    db_file = tmp_path / "MemPalace" / "memory.sqlite"
    assert db_file.exists()

    # Verify retrieval against newly initialized DB
    conn = storage.connect(db_file)
    try:
        search_res = retrieval.search(conn, "welcome", mode="bm25", limit=3)
        assert len(search_res.hits) >= 1
        assert "welcome" in search_res.hits[0].title.lower()
    finally:
        conn.close()


def test_initialize_workspace_claude_flavor(tmp_path: Path) -> None:
    cfg = WorkspaceInitializerConfig(
        workspace=tmp_path,
        agent_flavor=AgentFlavor.CLAUDE,
        seed_essences=False,
        install_skills=False,
        setup_decisions=False,
    )
    report = initialize_workspace(cfg)

    assert (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "docs" / "decisions").exists()
    assert not (tmp_path / ".agents").exists()
    assert report.db_initialized


def test_initialize_workspace_idempotent(tmp_path: Path) -> None:
    cfg = WorkspaceInitializerConfig(
        workspace=tmp_path,
        agent_flavor=AgentFlavor.GENERIC,
    )
    report1 = initialize_workspace(cfg)
    assert len(report1.created_paths) > 0

    # Second run should report existing paths
    report2 = initialize_workspace(cfg)
    assert len(report2.existing_paths) > 0
    assert (tmp_path / "MEMPALACE_KICKOFF.md").exists()


def test_initialize_workspace_dry_run(tmp_path: Path) -> None:
    cfg = WorkspaceInitializerConfig(
        workspace=tmp_path,
        agent_flavor=AgentFlavor.OPENCODE,
        dry_run=True,
    )
    report = initialize_workspace(cfg)
    assert report.db_initialized
    assert not (tmp_path / "MemPalace").exists()
    assert not (tmp_path / "MEMPALACE_KICKOFF.md").exists()


def test_cli_init_workspace_agent_mode(tmp_path: Path, cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(
        app,
        [
            "init-workspace",
            "--workspace",
            str(tmp_path),
            "--agent",
            "--agent-flavor",
            "antigravity",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["workspace"] == str(tmp_path.resolve())
    assert data["agent_flavor"] == "antigravity"
    assert data["db_initialized"] is True
    assert (tmp_path / "MEMPALACE_KICKOFF.md").exists()


def test_cli_setup_alias(tmp_path: Path, cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(
        app,
        [
            "setup",
            "--workspace",
            str(tmp_path),
            "--agent",
            "--agent-flavor",
            "opencode",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["agent_flavor"] == "opencode"
    assert (tmp_path / "AGENTS.md").exists()


def test_cli_init_workspace_invalid_agent(tmp_path: Path, cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(
        app,
        [
            "init-workspace",
            "--workspace",
            str(tmp_path),
            "--agent",
            "--agent-flavor",
            "nonexistent_bot",
        ],
    )
    assert result.exit_code == 2


def test_cli_init_workspace_interactive_simulation(
    tmp_path: Path, cli_runner: CliRunner
) -> None:

    # Simulated answers:
    # 1. Target workspace path: tmp_path
    # 2. Choose agent: 1 (antigravity)
    # 3. Seed essence: y
    # 4. Install skill: y
    # 5. Scaffold decisions: y
    # 6. Generate setup scripts: y
    user_inputs = f"{tmp_path}\n1\ny\ny\ny\ny\n"
    result = cli_runner.invoke(
        app,
        ["init-workspace", "--human"],
        input=user_inputs,
    )
    assert result.exit_code == 0, result.output
    assert "Workspace initialized successfully!" in result.output
    assert "MEMPALACE KICK-OFF PROMPT" in result.output
    assert (tmp_path / "MemPalace" / "memory.sqlite").exists()
    assert (tmp_path / "scripts" / "setup-mempalace.ps1").exists()
    assert (tmp_path / "MEMPALACE_KICKOFF.md").exists()

