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

from mempalace import config, ingest, retrieval, storage
from mempalace.embeddings import Embedder, EmbeddingError


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

Essence files (`YYYY-MM-DD-slug.md`) are the **single source of truth** for semantic agent memory.
Each essence captures a non-obvious pitfall, architectural preference, or thinking style.

## Deterministic Qualification Rubric
A candidate qualifies for `MemPalace/essences/` only if it passes all three gates:
- **Tooling Invisibility ($I \\ge 2$)**: Cannot be prevented by a linter rule or type check alone.
- **Blast Radius ($B \\ge 2$)**: Affects more than a single isolated helper function.
- **Composite Score ($S \\ge 3.2$)**: $S = 0.35B + 0.30R + 0.20P + 0.15I$ (1-5 scale for
  Blast Radius $B$, Root-Cause Depth $R$, Reproducibility $P$, and Tooling Invisibility $I$).

## Rules
- **English-only**: Workspace policy requires English text.
- **Header metadata**: Include `Date: YYYY-MM-DD`, `Category: pitfall|preference|thinking_style`,
  and optional `Status: active|superseded|deprecated` (or equivalent YAML frontmatter).
- **Derived SQLite store**: The database (`MemPalace/memory.sqlite`) is derived via:
  ```bash
  mempalace ingest
  ```
"""

_DECISION_README = """# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for this workspace.
Records document irreversible or high-migration-cost (Type 1) architectural choices.

## Rules
- Create new records using `template.md`.
- File naming convention: `ADR-NNN-short-slug.md`.
- Valid lifecycle statuses: `draft`, `proposed`, `active`, `accepted`, `rejected`,
  `deprecated`, `superseded`.
- When superseding a prior ADR, update both files bidirectionally (`Supersedes: ADR-NNN`
  and `Superseded-by: ADR-MMM`).
- Register decisions into MemPalace with:
  ```bash
  mempalace register-decisions
  ```
"""

_DECISION_TEMPLATE = """# ADR-NNN: Title

Date: YYYY-MM-DD
Status: proposed|active|accepted|rejected|deprecated|superseded
Tags: tag1, tag2
Deciders: author
Supersedes: None
Superseded-by: None

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

_SETUP_PS1_TEMPLATE = """<#
.SYNOPSIS
MemPalace v2 automated environment setup and verification script for Windows PowerShell.
#>
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
    mempalace embed
} else {
    Write-Host "⚠️ 'mempalace' installed. Running via uv tool run:" -ForegroundColor Yellow
    uv tool run mempalace doctor
    uv tool run mempalace ingest
    uv tool run mempalace embed
}

Write-Host "`n✨ MemPalace environment setup complete! Your workspace is ready.`n" `
    -ForegroundColor Green
"""

_SETUP_SH_TEMPLATE = """#!/usr/bin/env bash
# @description: MemPalace v2 automated environment setup and verification script (POSIX/Bash).
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
    mempalace embed
else
    echo -e "\\033[1;33m⚠️ 'mempalace' installed. Running via uv tool run:\\033[0m"
    uv tool run mempalace doctor
    uv tool run mempalace ingest
    uv tool run mempalace embed
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

# SKILL: MemPalace 4-Entity Synchronization (proposal-first)

## Purpose
Agentic memory routine for **Semantic Essences**, **Episodic Sessions**, and **Tools**.
**The agent proposes semantic lessons; the user decides what gets written.**

## 1. Semantic Memory (`MemPalace/essences/*.md`) — Proposal-First
A candidate lesson qualifies for `MemPalace/essences/` if and only if it passes all three gates:
- **Tooling Invisibility ($I \\ge 2$)**: Cannot be caught by a linter rule or type check alone.
- **Blast Radius ($B \\ge 2$)**: Extends beyond a single internal function.
- **Composite Score ($S \\ge 3.2$)**: $S = 0.35B + 0.30R + 0.20P + 0.15I$ (1-5 scale).

### Proposal Protocol
1. **Search** for an existing essence covering the candidate:
   ```bash
   mempalace search --mode hybrid "<query>"
   ```
2. **Classify** candidate: `pitfall` | `preference` | `thinking_style` and compute score $S$.
3. **Present** a compact block at the end of your reply:
   ```text
   🧠 MemPalace candidates (1)
   1. [pitfall | S=3.65 (B=3,R=4,P=4,I=4)] description -> essence YYYY-MM-DD-slug.md
   Reply "write 1" / "skip" / "edit" - nothing is written until you confirm.
   ```
4. Write only after user approves, then run `mempalace ingest`.

## 2. Episodic Memory (`MemPalace/sessions.jsonl`) — Session Closure
When closing out a non-trivial task, bug investigation, or feature implementation, record a
condensed episodic session log (persisted to `MemPalace/sessions.jsonl` and indexed in SQLite):
```bash
mempalace sync --id "<YYYY-MM-DD-short-topic>" \\
  --summary "<1-2 sentence summary of task, lessons, and outcome>" \\
  --tags "<comma-separated tags>"
```

## 3. Procedural Memory (`tools/`, `scripts/`) & Hygiene
- Before creating a new utility script, search registered workspace tools:
  ```bash
  mempalace search --source tool "<capability>"
  ```
- After adding or updating tools under `tools/<subdir>/` or `scripts/`, run:
  ```bash
  mempalace register-tools
  ```
- When `mempalace doctor` warns that stale/archived records reached the threshold ($\\ge 20$),
  run `mempalace sweep` to evict stale vectors and optimize FTS5.
"""

_DECISION_MAKING_SKILL = """---
name: decision-making
description: Record, review, supersede, and register architecture decisions (ADRs) in MemPalace.
tags:
  - adr
  - architecture
  - governance
---

# SKILL: Decision Making and ADR Lifecycle Governance

## Trigger (Type 1 Decisions Only)
Create an ADR in `docs/decisions/ADR-NNN-short-slug.md` for irreversible or high-migration-cost
architectural choices (storage engines, model runtimes, CLI/API contracts, core dependencies).
Routine refactors and local bugfixes belong in commits or specs, not ADRs.

## ADR Lifecycle & Supersession
- Valid statuses: `draft`, `proposed`, `active`, `accepted`, `rejected`, `deprecated`, `superseded`.
- Default search (`mempalace search`) surfaces only `active` and `accepted` decisions.
  Use `mempalace search --include-archived "<query>"` to inspect historical/superseded ADRs.
- When superseding an ADR, update **both** records bidirectionally:
  - New ADR header: `Supersedes: ADR-NNN`
  - Old ADR header: `Status: superseded` and `Superseded-by: ADR-MMM`
- After creating or updating an ADR, run:
  ```bash
  mempalace register-decisions
  ```
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
## MemPalace Unified 4-Entity Memory & ADR Governance Protocol

This workspace uses **MemPalace v2** for persistent cross-session memory across 4 entity stores:
- **Target Agent**: `{flavor.value}`
- **1. Semantic Memory (Wisdom)**: `MemPalace/essences/*.md` (single source of truth)
- **2. Architectural Memory (Decisions)**: `docs/decisions/ADR-NNN-*.md`
- **3. Episodic Memory (Sessions)**: `MemPalace/sessions.jsonl`
- **4. Procedural Memory (Tools)**: `tools/<subdir>/` and `scripts/*`
- **Derived SQLite DB**: `MemPalace/memory.sqlite`
- **Environment Doctor**: `mempalace doctor`
- **Setup Script**: `scripts/setup-mempalace.ps1` (Windows) / `scripts/setup-mempalace.sh` (POSIX)

### Operational Rules for Agents:
0. **Verify Environment**: Run `mempalace doctor` if memory commands fail;
   execute the workspace setup script (`scripts/setup-mempalace.ps1`/`.sh`) to bootstrap.
1. **Query Before Starting**: Before starting complex tasks or writing new scripts, query memory:
   ```bash
   mempalace search --mode hybrid "<query>"
   mempalace search --source tool "<capability>"
   ```
2. **Deterministic Essence Qualification (Proposal-First)**:
   Propose a candidate for `MemPalace/essences/` only if it passes all three gates:
   - **Tooling Invisibility ($I \\ge 2$)**: Cannot be caught by a linter rule or type check alone.
   - **Blast Radius ($B \\ge 2$)**: Extends beyond a single internal function.
   - **Composite Score ($S \\ge 3.2$)**: $S = 0.35B + 0.30R + 0.20P + 0.15I$ (1-5 scale).
   Do not write essences without explicit user confirmation.
3. **ADR Lifecycle Governance**:
   Record Type 1 irreversible architectural decisions in `docs/decisions/ADR-NNN-*.md` using
   lifecycle statuses (`draft`, `proposed`, `active`, `accepted`, `rejected`, `deprecated`,
   `superseded`) and bidirectional supersession (`Supersedes:` / `Superseded-by:`).
4. **Episodic Session & Procedural Tool Sync**:
   - At task/session closure, record a condensed session summary:
     `mempalace sync --id "<session-id>" --summary "<summary>" --tags "<tags>"`
   - After adding/editing essences, ADRs, or tools, refresh the index:
     ```bash
     mempalace ingest
     ```
   - When `mempalace doctor` warns of stale/archived count ($\\ge 20$), run `mempalace sweep`.
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
            "- Follow `.agents/skills/memory-sync/SKILL.md` and "
            "`.agents/skills/decision-making/SKILL.md`.\n"
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

    return f"""Hello! I have integrated **MemPalace v2** into {ws_name} for 4-entity agent memory.

### 0. Environment Prerequisite & Self-Healing:
- **Diagnostic Check**: Run `mempalace doctor` to verify your environment and database status.
- **If `mempalace` command is missing**: Run the automated setup script:
  - Windows (PowerShell): `.\\scripts\\setup-mempalace.ps1`
  - Linux / macOS (Bash): `./scripts/setup-mempalace.sh`
  - Or manually install via uv: `uv tool install git+https://github.com/aruruka/mempalace.git`

### 1. Your 4-Entity Memory Instructions:
1. **Four Memory Stores**:
   - **Wisdom (`MemPalace/essences/*.md`)**: Semantic pitfalls, preferences, and thinking styles.
   - **Decisions (`docs/decisions/ADR-NNN-*.md`)**: Type 1 ADRs (`active`/`superseded`).
   - **Sessions (`MemPalace/sessions.jsonl`)**: Condensed episodic task logs (`mempalace sync`).
   - **Tools (`tools/<subdir>/`, `scripts/*`)**: Workspace scripts (`mempalace register-tools`).
2. **Querying Memory**: Before starting complex tasks or creating scripts, search memory:
   ```bash
   mempalace search --mode hybrid "<keywords>"
   mempalace search --source tool "<capability>"
   ```
3. **Proposal-First Essence Protocol & Session Sync**:
   - Do NOT silently edit essence files.
   - Qualify candidates via $S = 0.35B + 0.30R + 0.20P + 0.15I \\ge 3.2$ ($I \\ge 2, B \\ge 2$):
     `🧠 MemPalace candidate: [pitfall/preference/thinking_style | S=...] <summary>`
   - Once approved, save to `MemPalace/essences/YYYY-MM-DD-slug.md` (English-only) and run:
     ```bash
     mempalace ingest
     ```
   - At task closure, log the session via `mempalace sync --id "<id>" --summary "<summary>"`.
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
    embed: bool = True
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
    vectors_indexed: int = 0
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

    # 5. Install memory-sync and decision-making skills if requested
    if cfg.install_skills:
        skill_file = ws / ".agents" / "skills" / "memory-sync" / "SKILL.md"
        _write_file(skill_file, _MEMORY_SYNC_SKILL)
        decision_skill = ws / ".agents" / "skills" / "decision-making" / "SKILL.md"
        _write_file(decision_skill, _DECISION_MAKING_SKILL)

    # 6. Install automated setup scripts if requested
    if cfg.setup_scripts:
        scripts_dir = ws / "scripts"
        if not cfg.dry_run:
            scripts_dir.mkdir(parents=True, exist_ok=True)
        _write_file(scripts_dir / "setup-mempalace.ps1", _SETUP_PS1_TEMPLATE)
        _write_file(scripts_dir / "setup-mempalace.sh", _SETUP_SH_TEMPLATE)

    # 7. Initialize SQLite DB and run initial ingest + embedding
    db_path = config.resolve_db(ws, None)
    if not cfg.dry_run:
        conn = storage.connect(db_path)
        try:
            storage.init_db(conn)
            report.db_initialized = True
            # Perform initial ingest to index the starter essence & ADRs
            ingest_rep = ingest.ingest_all(conn, ws, migrate=False)
            report.docs_indexed = ingest_rep.docs_indexed
            if cfg.embed:
                try:
                    embedder = Embedder()
                    report.vectors_indexed = retrieval.ensure_vectors(conn, embedder)
                except EmbeddingError:
                    report.vectors_indexed = 0
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
