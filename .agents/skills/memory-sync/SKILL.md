---
name: memory-sync
description: Propose-and-confirm routine for writing session lessons (pitfalls, preferences, thinking styles), episodic logs, and workspace tools into MemPalace.
tags:
  - memory
  - mempalace
  - sync
---

# SKILL: MemPalace 4-Entity Synchronization (proposal-first)

## Purpose
Agentic memory routine governing **Semantic Essences (`wisdom`)**, **Episodic Sessions (`sessions`)**, and **Procedural Tools (`tool_registry`)**.
**The agent proposes what is worth remembering in `MemPalace/essences/`; the user decides what gets written.**

## 1. Semantic Memory (`MemPalace/essences/*.md`) — Deterministic Qualification
A candidate lesson qualifies for `MemPalace/essences/` if and only if it passes all three gates:
- **Tooling Invisibility ($I \ge 2$)**: Cannot be prevented by a compiler flag, linter rule, or type check alone.
- **Blast Radius ($B \ge 2$)**: Extends beyond a single isolated helper function.
- **Composite Score ($S \ge 3.2$)**: Calculated as $S = 0.35B + 0.30R + 0.20P + 0.15I$, where $B$ (Blast Radius), $R$ (Root-Cause Depth), $P$ (Reproducibility), and $I$ (Tooling Invisibility) are scored on a $1\text{--}5$ scale.

### When NOT to propose
- Content already captured in committed code, ADRs, or wiki pages.
- Secrets / API keys / credentials; transient state; step-by-step task bookkeeping.
- Duplicates of an existing essence (search first: `uv run python -m mempalace search --mode hybrid "kw"`).
- Pure routine edits or refactors with $S < 3.2$.

### Proposal Protocol
1. **Search** for an existing essence covering the candidate (avoid duplicates; decide new vs update).
2. **Classify** each candidate (`pitfall` | `preference` | `thinking_style`) and compute its deterministic score $S$.
3. **Present** a compact block at the end of the reply:
   ```text
   🧠 MemPalace candidates (1)
   1. [pitfall | S=3.65 (B=3,R=4,P=4,I=4)] fastembed token truncation on long docs -> essence 2026-09-05-fastembed-truncation.md
   Reply "write 1" / "skip" / "edit" - nothing is written until you confirm.
   ```
4. **Write** (only after user confirmation):
   - Create `MemPalace/essences/YYYY-MM-DD-slug.md` (English-only; include `Date:`, `Category:`, and optional `Status: active|superseded|deprecated`).
   - Sync the derived DB + search index: `uv run python -m mempalace ingest` (and `uv run python -m mempalace embed` if dense vectors are needed).

## 2. Episodic Memory (`MemPalace/sessions.jsonl`) — Session Closure
When wrapping up a non-trivial task, investigation, or feature branch, record a condensed episodic summary (dual-written to `MemPalace/sessions.jsonl` and SQLite `sessions`):
```bash
uv run python -m mempalace sync --id "<YYYY-MM-DD-short-topic>" \
  --summary "<1-2 sentence summary of task, lessons, and outcome>" \
  --tags "<comma-separated tags>"
```

## 3. Procedural Memory (`tools/`, `scripts/`) & Batched Hygiene Sweeps
- **Reuse Before Writing**: Before creating a new script or tool, search registered workspace tools:
  ```bash
  uv run python -m mempalace search --source tool "<capability>"
  ```
- **Register Tools**: After adding or modifying tools in `tools/<subdir>/` or `scripts/*.{py,ps1,sh}`, run:
  ```bash
  uv run python -m mempalace register-tools
  ```
- **Hygiene Sweep**: When `mempalace doctor` reports that non-active (`superseded`, `deprecated`, `removed`, `archived`) records reached the threshold ($\ge 20$), run:
  ```bash
  uv run python -m mempalace sweep
  ```


