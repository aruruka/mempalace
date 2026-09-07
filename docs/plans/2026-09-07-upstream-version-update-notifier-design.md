# Technical Design: Upstream Version Update Notifier for MemPalace

> **Status:** Validated  
> **Date:** 2026-09-07  
> **Author:** Antigravity (Pair Programming Brainstorming)  

---

## 1. Executive Summary & Understanding

- **Purpose**: Notify developers and coding agents working in downstream workspaces (such as `tools_on_windows`) whenever an upstream release or tag is published in `aruruka/mempalace` on GitHub.
- **Audience**: Coding agents and developers running `mempalace` workflows.
- **Workflow**:
  1. A user/agent runs a `mempalace` command in a workspace.
  2. `mempalace` checks if a newer upstream version is available using a local cache.
  3. If newer, a non-intrusive notification banner is printed to `sys.stderr`.
  4. The coding agent notices the banner and asks the user: *"A newer version of mempalace (v0.x.x) is available. Would you like to update?"*
  5. Upon user confirmation, the agent runs the recommended update command.

---

## 2. Key Constraints & Non-Goals

### Constraints
- **Zero Disruption**: Must never block, crash, or delay primary workflows if offline, rate-limited, DNS fails, or requests time out.
- **Clean Output Stream**: Written strictly to `sys.stderr` to keep `stdout` (e.g., JSON outputs or piped streams) uncorrupted.
- **Throttling**: Maximum 1 network check per 24 hours per workspace via `MemPalace/.cache.json`.
- **Zero Heavy Dependencies**: Pure Python standard library (`urllib.request`, `json`, `sys.stderr`, `os`, `pathlib`).

### Explicit Non-Goals
- Autonomous in-place updating or editing of consumer manifest files (`pyproject.toml`) without user approval.
- Background persistent daemon processes or threads.
- Transmitting telemetry, IP tracking, or workspace metrics upstream.

---

## 3. Assumptions

1. The authoritative upstream source is the public GitHub repository releases/tags (`https://api.github.com/repos/aruruka/mempalace/releases/latest`).
2. Downstream workspaces store workspace memory inside `MemPalace/`. The cache file `MemPalace/.cache.json` resides here and is gitignored.
3. Network calls have a hard 1.5-second socket timeout. On any exception, silent failure occurs and back-off is applied.
4. Setting `MEMPALACE_NO_UPDATE_CHECK=1` or `CI=1` completely bypasses the check.

---

## 4. Decision Log

| ID | Decision | Considered Options | Rationale |
| :--- | :--- | :--- | :--- |
| **DEC-001** | **Agent-assisted execution** | 1. Auto-edit `pyproject.toml`<br>2. Agent-assisted command execution<br>3. In-place git switch | Keeps `mempalace` simple and clean; avoids corrupting consumer manifest files while keeping human-in-the-loop control. |
| **DEC-002** | **Workspace cache file** | 1. SQLite metadata table<br>2. `MemPalace/.cache.json`<br>3. User home directory cache | Works regardless of whether DB is initialized, scoped strictly to workspace, easy to gitignore. |
| **DEC-003** | **Inline check with strict timeout** | 1. Inline with 1.5s timeout<br>2. Background daemon thread<br>3. Manual-only command | Prevents thread lifecycle/daemon issues in CLI processes while ensuring zero perceptible lag. |
| **DEC-004** | **`stderr` banner delivery** | 1. `stderr` banner<br>2. Dual-mode JSON/stderr<br>3. Specific lifecycle commands only | Keeps `stdout` data streams (JSON, piping) clean while remaining directly visible to both humans and agents. |
| **DEC-005** | **Upstream Check via GitHub API** | 1. GitHub API (Approach A)<br>2. `git ls-remote` (Approach B)<br>3. Raw file fetch (Approach C) | Approach A uses stdlib HTTP with no subprocess overhead or git credential hang risks on Windows. |

---

## 5. Architectural Design

### 5.1 Component Structure

Module: `src/mempalace/notifier.py`

```
                          ┌────────────────────────┐
                          │  CLI Entrypoint (Typer)│
                          │   (ingest, search, ...) │
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │  UpdateNotifier        │
                          │  - check_for_update()  │
                          └─────┬────────────┬─────┘
           read/write cache     │            │ check upstream if TTL expired
                                ▼            ▼
             ┌─────────────────────┐      ┌───────────────────────────┐
             │ MemPalace/.cache.json│     │ GitHub API (1.5s timeout) │
             │  (TTL: 86400s)       │     │ /repos/.../releases/latest│
             └─────────────────────┘      └───────────────────────────┘
                                                     │
                                                     ▼ (if newer version available)
                                          ┌───────────────────────────┐
                                          │ sys.stderr Banner Output  │
                                          └───────────────────────────┘
```

1. **`UpdateCache`**: Reads and writes `MemPalace/.cache.json`.
   - Schema:
     ```json
     {
       "last_checked_at": 1757235000,
       "latest_version": "0.3.0"
     }
     ```
2. **`GitHubVersionChecker`**:
   - URL: `https://api.github.com/repos/aruruka/mempalace/releases/latest`
   - Headers: `{"User-Agent": "mempalace/<current_version>", "Accept": "application/vnd.github.v3+json"}`
   - Timeout: 1.5 seconds.
3. **`SemverComparator`**:
   - Parses tuples `(major, minor, patch)` to compare versions reliably.
4. **`NoticeRenderer`**:
   - Renders box banner to `sys.stderr`.

### 5.2 Banner Specification (`sys.stderr`)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ mempalace update available: v0.2.1 -> v0.3.0                           │
│ To update in your workspace:                                           │
│   uv add git+https://github.com/aruruka/mempalace.git --tag v0.3.0     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Gherkin BDD Contract (`tests/features/update_notifier.feature`)

```gherkin
Feature: Upstream Version Update Notifier
  As an agent or developer working in a downstream workspace
  I want MemPalace to notify me when an upstream update is available
  So that I can prompt the user to upgrade without disrupting operations

  Scenario: Cache hit with a newer version displays notice without network call
    Given a workspace with cached version "0.3.0" checked 1 hour ago
    When I run a mempalace CLI command
    Then stderr displays an update banner suggesting "v0.3.0"
    And stdout remains clean and uncorrupted

  Scenario: Expired cache performs network check and caches latest release
    Given a workspace with no cache or an expired cache
    And upstream GitHub reports latest release "0.3.0"
    When I run a mempalace CLI command
    Then "MemPalace/.cache.json" is updated with "0.3.0"
    And stderr displays an update banner suggesting "v0.3.0"

  Scenario: Network failure or timeout fails silently
    Given a workspace with an expired cache
    And upstream GitHub is unreachable or times out
    When I run a mempalace CLI command
    Then the command succeeds with exit code 0
    And no error or trace is shown to the user
    And the check backs off without blocking the operation

  Scenario: Update check is disabled via environment variable
    Given the environment variable "MEMPALACE_NO_UPDATE_CHECK" is set to "1"
    When I run a mempalace CLI command
    Then no update check or banner is emitted to stderr
```
