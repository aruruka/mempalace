"""Workspace initializer domain logic for MemPalace v2.

Provides scaffolding, starter essence generation, agent instruction synthesis,
and tailored kick-off prompts for coding agents (OpenCode, Hermes, Antigravity,
Claude Code, Cursor, and Generic agents).
"""

from __future__ import annotations

import datetime
import enum
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mempalace import config, ingest, storage


class AgentFlavor(enum.StrEnum):
    """Supported coding agent types for workspace integration."""

    OPENCODE = "opencode"
    HERMES = "hermes"
    ANTIGRAVITY = "antigravity"
    CLAUDE = "claude"
    CURSOR = "cursor"
    GENERIC = "generic"


SUPPORTED_AGENTS: list[str] = [f.value for f in AgentFlavor]

_ESSENCE_README = """# MemPalace Essences

Essence files (`*.md`) are the **single source of truth** for agent memory.
Each essence represents a hard-won pitfall, architectural preference, or style.

## Rules
- **English-only**: Workspace policy requires English text.
- **Derived SQLite store**: The database (`MemPalace/memory.sqlite`) is derived
  from these files via:
  ```bash
  mempalace ingest
  ```
- **Syncing memory**: Run `mempalace ingest` after creating or editing essences.
"""

_DECISION_README = """# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for this workspace.
Records document key architectural choices, context, trade-offs, and consequences.

## Rules
- Create new records using `template.md`.
- File naming convention: `ADR-NNN-short-slug.md`.
- Register decisions into MemPalace with:
  ```bash
  mempalace register-decisions
  ```
"""

_DECISION_TEMPLATE = """# ADR-NNN: Title

Date: YYYY-MM-DD
Status: active
Tags: tag1, tag2
Deciders: author

## Context
What is the problem or architectural context?

## Decision Drivers
- Driver 1
- Driver 2

## Options Considered
1. Option A: Pros and Cons
2. Option B: Pros and Cons

## Decision
What was chosen and why?

## Consequences
- Positive consequences
- Negative consequences / trade-offs

## Related Decisions
- None
"""

_SETUP_PS1_TEMPLATE = """# MemPalace v2 Environment Setup & Verification Script (Windows PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "`n🏰 MemPalace v2 — Automated Environment Setup`n" -ForegroundColor Cyan
Write-Host "Checking runtime prerequisites..." -ForegroundColor DarkGray

# 1. Check for uv
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv package manager..." -ForegroundColor Yellow
    irm https://astral.sh/uv/install.ps1 | iex
    $userPath = [System.Environment]::GetEnvironmentVariable("Path","User")
    $sysPath = [System.Environment]::GetEnvironmentVariable("Path","Machine")
    $env:Path = "$userPath;$sysPath"
}

if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Error: 'uv' not found in PATH. Visit https://docs.astral.sh/uv/." `
        -ForegroundColor Red
    exit 1
}

Write-Host "✅ uv toolchain verified." -ForegroundColor Green

# 2. Install or upgrade mempalace CLI tool
Write-Host "Installing/updating mempalace CLI tool..." -ForegroundColor Cyan
uv tool install mempalace --force 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing from git repository..." -ForegroundColor DarkGray
    uv tool install git+https://github.com/aruruka/mempalace.git --force
}

# 3. Verify mempalace command & run doctor
Write-Host "`nRunning environment diagnostics..." -ForegroundColor Cyan
if (Get-Command "mempalace" -ErrorAction SilentlyContinue) {
    mempalace doctor
    mempalace ingest
} else {
    Write-Host "⚠️ 'mempalace' installed. Running via uv tool run:" -ForegroundColor Yellow
    uv tool run mempalace doctor
    uv tool run mempalace ingest
}

Write-Host "`n✨ MemPalace environment setup complete! Your workspace is ready.`n" `
    -ForegroundColor Green
"""

_SETUP_SH_TEMPLATE = """#!/usr/bin/env bash
# MemPalace v2 Environment Setup & Verification Script (POSIX / macOS / Linux)
set -euo pipefail

echo -e "\\n\\033[1;36m🏰 MemPalace v2 — Automated Environment Setup\\033[0m\\n"
echo "Checking runtime prerequisites..."

# 1. Check for uv
if ! command -v uv &> /dev/null; then
    echo -e "\\033[1;33mInstalling uv (Astral's ultra-fast Python package manager)...\\033[0m"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

if ! command -v uv &> /dev/null; then
    echo -e "\\033[1;31m❌ Error: 'uv' not found in PATH. Please install uv from https://docs.astral.sh/uv/.\\033[0m"
    exit 1
fi

echo -e "\\033[1;32m✅ uv toolchain verified.\\033[0m"

# 2. Install/upgrade mempalace CLI tool
echo -e "\\033[1;36mInstalling/updating mempalace CLI tool...\\033[0m"
if ! uv tool install mempalace --force 2>/dev/null; then
    echo "Installing from git repository..."
    uv tool install git+https://github.com/aruruka/mempalace.git --force
fi

export PATH="$HOME/.local/bin:$PATH"

# 3. Verify mempalace command & run doctor
echo -e "\\n\\033[1;36mRunning environment diagnostics...\\033[0m"
if command -v mempalace &> /dev/null; then
    mempalace doctor
    mempalace ingest
else
    echo -e "\\033[1;33m⚠️ 'mempalace' installed. Running via uv tool run:\\033[0m"
    uv tool run mempalace doctor
    uv tool run mempalace ingest
fi

echo -e "\\n\\033[1;32m✨ MemPalace environment setup complete! Your workspace is ready.\\033[0m\\n"
"""

_MEMORY_SYNC_SKILL = """---
name: memory-sync
description: Propose-and-confirm routine for writing session lessons into MemPalace.
tags:
  - memory
  - mempalace
  - sync
---

# SKILL: MemPalace Synchronization (proposal-first)

## Purpose
Agentic memory routine for durable long-term context.
**The agent proposes what is worth remembering; the user decides what gets written.**
Nothing is written to `MemPalace/essences/` without explicit user confirmation.

## When to propose (candidate events)
A task produced a MemPalace candidate when it satisfies **at least one** of:
- **Fix with a root cause**: an error was hit, the *why* was found, and the fix
  is not already captured in code or an existing essence.
- **New canonical path or preference**: a decision about *how this workspace does things*
  (tool usage, testing rules, config patterns).
- **Component evaluated or added**: new package dependency, algorithm evaluation,
  or CLI feature with a lesson.
- **Cross-file insight**: knowledge spanning files that would be lost by reading any single file.
- **Hard-won, non-obvious fact**: something rediscovered this session that will cost time again.

## Proposal protocol
1. **Search** for an existing essence covering the candidate:
   ```bash
   mempalace search --mode hybrid "<query>"
   ```
2. **Classify** candidate: `pitfall` | `preference` | `thinking_style`.
3. **Present** a compact block at the end of your reply:
   ```text
   🧠 MemPalace candidates (1)
   1. [pitfall] description -> essence YYYY-MM-DD-slug.md
   Reply "write 1" / "skip" / "edit" - nothing is written until you confirm.
   ```
4. Write only after user approves, then run `mempalace ingest`.
"""


def parse_agent_flavor(val: str | None) -> AgentFlavor:
    """Parse a user-supplied string into a supported AgentFlavor.

    Args:
        val: Agent name string or None.

    Returns:
        The matched AgentFlavor, or AgentFlavor.GENERIC if empty.

    Raises:
        ValueError: If val does not match any supported flavor.
    """
    if not val:
        return AgentFlavor.GENERIC
    cleaned = val.strip().lower()
    for flavor in AgentFlavor:
        if flavor.value == cleaned:
            return flavor
    if "gemini" in cleaned or "antigravity" in cleaned:
        return AgentFlavor.ANTIGRAVITY
    if "claude" in cleaned or "anthropic" in cleaned:
        return AgentFlavor.CLAUDE
    if "opencode" in cleaned:
        return AgentFlavor.OPENCODE
    if "hermes" in cleaned:
        return AgentFlavor.HERMES
    if "cursor" in cleaned:
        return AgentFlavor.CURSOR
    if "generic" in cleaned or "universal" in cleaned:
        return AgentFlavor.GENERIC

    valid = ", ".join(SUPPORTED_AGENTS)
    raise ValueError(f"Unknown agent flavor '{val}'. Supported options: {valid}")


def generate_starter_essence() -> str:
    """Generate the content of a welcome starter essence."""
    today = datetime.date.today().isoformat()
    return f"""# Welcome to MemPalace

Date: {today}
Category: preference

Welcome to MemPalace v2! This workspace now has persistent agent memory.

## Core Rules
1. **Source of truth**: Essence files in `MemPalace/essences/` are the single source of truth.
2. **Derived index**: The SQLite database (`MemPalace/memory.sqlite`) is a rebuildable index.
3. **Proposal-first**: Coding agents propose lessons at session checkpoints;
   the developer decides what gets committed.
4. **Ingest cycle**: After editing essences, run `mempalace ingest`.
"""


def generate_agent_rules(flavor: AgentFlavor) -> str:
    """Generate agent rule block for inclusion in AGENTS.md, CLAUDE.md, etc.

    Args:
        flavor: The target agent flavor.

    Returns:
        Markdown text describing the MemPalace protocol.
    """
    return f"""
<!-- BEGIN MEMPALACE INTEGRATION -->
## MemPalace Agent Memory Protocol

This workspace uses **MemPalace v2** for persistent cross-session memory.
- **Target Agent**: `{flavor.value}`
- **Memory Store**: `MemPalace/essences/*.md` (single source of truth)
- **Derived SQLite DB**: `MemPalace/memory.sqlite`
- **Environment Doctor**: `mempalace doctor`
- **Setup Script**: `scripts/setup-mempalace.ps1` (Windows) / `scripts/setup-mempalace.sh` (POSIX)

### Operational Rules for Agents:
0. **Verify Environment**: Run `mempalace doctor` if memory commands fail;
   execute the workspace setup script (`scripts/setup-mempalace.ps1`/`.sh`) to bootstrap.
1. **Query Before Starting**: Before starting complex tasks, query existing memories:
   ```bash
   mempalace search --mode hybrid "<query>"
   ```
2. **Proposal-First Memory**: At the end of sessions with significant lessons,
   propose memory candidates to the user. Do not write essences without confirmation.
3. **Ingest After Writing**: Whenever essence files or ADRs are updated, refresh the index:
   ```bash
   mempalace ingest
   ```
<!-- END MEMPALACE INTEGRATION -->
"""


def generate_kickoff_prompt(flavor: AgentFlavor, workspace: Path) -> str:
    """Generate a copy-pasteable kick-off prompt tailored to the target agent.

    Args:
        flavor: The target agent flavor.
        workspace: The root directory of the workspace.

    Returns:
        Formatted prompt string ready to send to the coding agent.
    """
    ws_name = workspace.name or "this workspace"
    flavor_specific = ""
    if flavor == AgentFlavor.ANTIGRAVITY:
        flavor_specific = (
            "- Follow the `.agents/skills/memory-sync/SKILL.md` skill for memory retention.\n"
            "- Check `AGENTS.md` for workspace rules and operating constraints."
        )
    elif flavor == AgentFlavor.CLAUDE:
        flavor_specific = (
            "- Review `CLAUDE.md` where MemPalace instructions have been appended.\n"
            "- Use bash tool execution to run `mempalace search`."
        )
    elif flavor == AgentFlavor.OPENCODE:
        flavor_specific = (
            "- Follow `AGENTS.md` protocol for cross-session knowledge persistence.\n"
            "- Query MemPalace whenever context from past tasks is relevant."
        )
    elif flavor == AgentFlavor.HERMES:
        flavor_specific = (
            "- MemPalace rules are configured in `AGENTS.md`.\n"
            "- Check memory before major refactors or tool executions."
        )
    elif flavor == AgentFlavor.CURSOR:
        flavor_specific = (
            "- MemPalace rules are linked in your workspace rules (`.cursorrules`).\n"
            "- Use terminal commands to query and ingest memory."
        )
    else:
        flavor_specific = (
            "- Review `AGENTS.md` or `MemPalace/essences/README.md` for conventions.\n"
            "- Always query memory before starting major tasks."
        )

    return f"""Hello! I have integrated **MemPalace v2** into {ws_name} for persistent agent memory.

### 0. Environment Prerequisite & Self-Healing:
- **Diagnostic Check**: Run `mempalace doctor` to verify your environment and database status.
- **If `mempalace` command is missing**: Run the automated setup script:
  - Windows (PowerShell): `.\\scripts\\setup-mempalace.ps1`
  - Linux / macOS (Bash): `./scripts/setup-mempalace.sh`
  - Or manually install via uv: `uv tool install git+https://github.com/aruruka/mempalace.git`

### 1. Your Memory Instructions:
1. **MemPalace Location**: Markdown files in `MemPalace/essences/*.md` are the source of truth.
   The SQLite DB at `MemPalace/memory.sqlite` provides hybrid search (BM25 + embeddings).
2. **Querying Memory**: Before starting complex tasks, search for past lessons:
   ```bash
   mempalace search --mode hybrid "<keywords>"
   ```
3. **Proposal-First Protocol**:
   - Do NOT silently edit essence files.
   - When a session uncovers an important lesson, propose candidate essences to me:
     `🧠 MemPalace candidate: [pitfall/preference/thinking_style] <summary>`
   - Once approved, save to `MemPalace/essences/YYYY-MM-DD-slug.md` (English-only) and run:
     ```bash
     mempalace ingest
     ```
{flavor_specific}

### 2. Immediate Verification Task:
Please run an environment check and a memory query right now to confirm your access:
```bash
mempalace doctor
mempalace search --mode bm25 "welcome"
```
Verify that all checks pass and you can see the starter essence, and let me know you are ready!
"""


def _empty_str_list() -> list[str]:
    """Return an empty list of strings (typed default for dataclasses)."""
    return []


@dataclass
class WorkspaceInitializerConfig:
    """Configuration options for initializing a workspace with MemPalace."""

    workspace: Path
    agent_flavor: AgentFlavor = AgentFlavor.GENERIC
    seed_essences: bool = True
    install_skills: bool = True
    setup_decisions: bool = True
    setup_scripts: bool = True
    kickoff_file: str | None = "MEMPALACE_KICKOFF.md"
    dry_run: bool = False


@dataclass
class WorkspaceInitializerReport:
    """Structured report produced by workspace initialization."""

    workspace: str
    agent_flavor: str
    created_paths: list[str] = field(default_factory=_empty_str_list)
    existing_paths: list[str] = field(default_factory=_empty_str_list)
    db_initialized: bool = False
    docs_indexed: int = 0
    kickoff_prompt_path: str = ""
    kickoff_prompt_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON output."""
        return asdict(self)


def initialize_workspace(cfg: WorkspaceInitializerConfig) -> WorkspaceInitializerReport:
    """Initialize a workspace with MemPalace directory structures, DB, and agent configuration.

    Args:
        cfg: Configuration parameters.

    Returns:
        A WorkspaceInitializerReport detailing all actions taken.
    """
    ws = cfg.workspace.resolve()
    report = WorkspaceInitializerReport(
        workspace=str(ws),
        agent_flavor=cfg.agent_flavor.value,
    )

    def _write_file(path: Path, content: str, append_if_exists: bool = False) -> None:
        rel = str(path.relative_to(ws))
        if path.exists():
            if append_if_exists:
                current = path.read_text(encoding="utf-8")
                if "BEGIN MEMPALACE INTEGRATION" not in current:
                    if not cfg.dry_run:
                        path.write_text(current.rstrip() + "\n" + content, encoding="utf-8")
                    report.created_paths.append(rel)
                else:
                    report.existing_paths.append(rel)
            else:
                report.existing_paths.append(rel)
        else:
            if not cfg.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            report.created_paths.append(rel)

    # 1. Scaffolding MemPalace/essences
    essence_dir = ws / "MemPalace" / "essences"
    if not cfg.dry_run:
        essence_dir.mkdir(parents=True, exist_ok=True)
    _write_file(essence_dir / "README.md", _ESSENCE_README)

    # 2. Seed starter essence if requested
    if cfg.seed_essences:
        today = datetime.date.today().isoformat()
        starter_path = essence_dir / f"{today}-welcome-to-mempalace.md"
        _write_file(starter_path, generate_starter_essence())

    # 3. Scaffolding docs/decisions if requested
    if cfg.setup_decisions:
        decisions_dir = ws / "docs" / "decisions"
        if not cfg.dry_run:
            decisions_dir.mkdir(parents=True, exist_ok=True)
        _write_file(decisions_dir / "README.md", _DECISION_README)
        _write_file(decisions_dir / "template.md", _DECISION_TEMPLATE)

    # 4. Agent instructions file (AGENTS.md, CLAUDE.md, .cursorrules)
    rules_content = generate_agent_rules(cfg.agent_flavor)
    if cfg.agent_flavor == AgentFlavor.CLAUDE:
        claude_md = ws / "CLAUDE.md"
        _write_file(claude_md, rules_content, append_if_exists=True)
    elif cfg.agent_flavor == AgentFlavor.CURSOR:
        cursor_rules = ws / ".cursorrules"
        _write_file(cursor_rules, rules_content, append_if_exists=True)
    else:
        agents_md = ws / "AGENTS.md"
        _write_file(agents_md, rules_content, append_if_exists=True)

    # 5. Install memory-sync skill if requested
    if cfg.install_skills:
        skill_file = ws / ".agents" / "skills" / "memory-sync" / "SKILL.md"
        _write_file(skill_file, _MEMORY_SYNC_SKILL)

    # 6. Install automated setup scripts if requested
    if cfg.setup_scripts:
        scripts_dir = ws / "scripts"
        if not cfg.dry_run:
            scripts_dir.mkdir(parents=True, exist_ok=True)
        _write_file(scripts_dir / "setup-mempalace.ps1", _SETUP_PS1_TEMPLATE)
        _write_file(scripts_dir / "setup-mempalace.sh", _SETUP_SH_TEMPLATE)

    # 7. Initialize SQLite DB and run initial ingest
    db_path = config.resolve_db(ws, None)
    if not cfg.dry_run:
        conn = storage.connect(db_path)
        try:
            storage.init_db(conn)
            report.db_initialized = True
            # Perform initial ingest to index the starter essence & ADRs
            ingest_rep = ingest.ingest_all(conn, ws, migrate=False)
            report.docs_indexed = ingest_rep.docs_indexed
        finally:
            conn.close()
    else:
        report.db_initialized = True

    # 8. Generate Kick-off prompt
    kickoff_content = generate_kickoff_prompt(cfg.agent_flavor, ws)
    report.kickoff_prompt_content = kickoff_content
    if cfg.kickoff_file:
        kickoff_path = ws / cfg.kickoff_file
        if not cfg.dry_run:
            kickoff_path.parent.mkdir(parents=True, exist_ok=True)
            kickoff_path.write_text(kickoff_content, encoding="utf-8")
        report.kickoff_prompt_path = str(kickoff_path.relative_to(ws))

    return report

