# ADR-010: Workspace Initializer and Agent Onboarding Protocol

Date: 2026-09-06
Status: active
Tags: onboarding, cli, initializer, scaffolding, agent-card, bdd
Deciders: aruruka, antigravity

## Context
MemPalace v2 is designed as an embedded memory engine that gives coding agents durable,
searchable, semantic recall across sessions. However, importing MemPalace into a new or
existing codebase previously required manual scaffolding of directory structures
(`MemPalace/essences/`), database schema initialization, and manual configuration of agent
instructions (`AGENTS.md`, `CLAUDE.md`, skills). Furthermore, coding agents (such as OpenCode,
Hermes, Antigravity, Claude Code, Cursor) lacked an immediate, actionable kick-off prompt
upon project installation to verify connectivity and adopt the proposal-first memory protocol.

## Decision Drivers
- **Zero-Friction Adoption**: External projects should be able to adopt MemPalace with a
  single `uvx` or `uv run` command in under 60 seconds.
- **Agent Alignment**: The onboarding experience must produce a structured, agent-specific
  "Kick-off Prompt" ready for developers to paste into their coding agent.
- **AI-Native CLI Contract**: Compliance with `ai-native-cli` specifications—supporting both
  an interactive wizard for humans (`--human` / TTY default) and a non-interactive JSON API
  for automated agents (`--agent`).
- **Minimal Dependencies**: Avoid heavy TUI frameworks (e.g. Textual, InquirerPy) to preserve
  instant execution when invoked via `uvx`.
- **Idempotency and Safety**: Initializing a workspace must never destroy or overwrite existing
  essences or user notes.

## Options Considered
### Option A: Manual Documentation Guide Only
- Pros: No code changes required.
- Cons: High error rate, friction, and lack of consistency across agent types.

### Option B: Heavyweight TUI Application (Textual / Curses)
- Pros: Rich terminal graphics and multi-page forms.
- Cons: Large dependency footprint, slow `uvx` launch time, poor headless/agent compatibility.

### Option C: Typer-based Dual Mode (Interactive Wizard + AI-Native JSON) with Domain Core
- Pros: Zero additional dependencies, lightning-fast `uvx` execution, full testability,
  dual human/agent persona support.
- Cons: Terminal interaction limited to prompts and styled blocks, which is completely
  sufficient for workspace scaffolding.

## Decision
Adopt **Option C**:
1. Implement `src/mempalace/initializer.py` as a pure, strictly-typed domain module handling
   scaffolding, starter templates, cross-platform setup scripts (`setup-mempalace.ps1`/`.sh`),
   agent configuration synthesis, and kick-off prompt generation.
2. Add `@app.command(name="init-workspace")` (with alias `@app.command(name="setup")`) and
   `@app.command(name="doctor")` in `src/mempalace/cli.py` with dual interactive/human and
   non-interactive/agent modes.
3. Generate agent-specific kick-off prompts tailored to OpenCode, Hermes, Antigravity,
   Claude Code, Cursor, and Generic coding agents with self-healing environment bootstrap guidance.
4. Feature the 60-second onboarding one-liner prominently at the top of `README.md`.
5. Enforce contract behavior via pytest-bdd in `tests/features/workspace_initializer.feature`.

## Rationale
Typer's native styling and prompt facilities provide a clean interactive experience without
bloating package dependencies. The dual mode aligns with the `ai-native-cli` specification,
making MemPalace usable by both human developers and autonomous agents.

## Consequences
### Positive
- One-liner adoption via `uvx --from git+... mempalace init-workspace` or `uv tool install`.
- Instant agent activation through copy-pasteable kick-off prompts (`MEMPALACE_KICKOFF.md`).
- Automated installation of the `memory-sync` proposal-first skill.
- Self-healing environment diagnostics via `mempalace doctor`.
- Automated cross-platform setup scripts (`scripts/setup-mempalace.ps1` & `.sh`).
- Full BDD test coverage ensuring stability and idempotence.

### Negative / Trade-offs
- The CLI surface increases by two commands (`init-workspace` and alias `setup`).
- Ongoing maintenance of prompt templates as coding agents evolve.

### Risks and Mitigations
- Risk: Running the initializer on an existing workspace could overwrite existing memory files.
  - Mitigation: `initialize_workspace()` checks for existing paths and appends integration
    markers rather than clobbering existing files.

## Related Decisions and References
- ADR-009: SQLite Hybrid Retrieval for MemPalace v2
- AGENTS.md: MemPalace Knowledge Schema & Agent Operating Rules
- AI-Native CLI Spec v0.1

## Supersession
- Supersedes: None
- Superseded by: None

