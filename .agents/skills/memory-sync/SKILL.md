---
name: memory-sync
description: Propose-and-confirm routine for writing session lessons (pitfalls, preferences, thinking styles) into MemPalace — the agent proposes, the user decides.
tags:
  - memory
  - mempalace
  - sync
---

# SKILL: MemPalace Synchronization (proposal-first)

## Purpose
Agentic memory routine for durable long-term context. **The agent proposes what is worth remembering; the user decides what gets written.** Nothing is written to `MemPalace/essences/` without explicit user confirmation.

## When to propose (candidate events)
A task produced a MemPalace candidate when it satisfies **at least one** of:
- **Fix with a root cause**: an error was hit, the *why* was found, and the fix is not already captured in code or an existing essence.
- **New canonical path or preference**: a decision about *how this workspace does things* (tool usage, testing rules, config patterns).
- **Component evaluated or added**: new package dependency, algorithm evaluation, or CLI feature with a lesson.
- **Cross-file insight**: knowledge spanning files that would be lost by reading any single file.
- **Hard-won, non-obvious fact**: something rediscovered this session that will cost time again.

**Session checkpoint**: once a session has lasted >=10 user turns *and* produced at least one candidate event, end the reply with a compact memory-review block.

## When NOT to propose
- Content already captured in committed code, ADRs, or wiki pages.
- Secrets / API keys / credentials; transient state; step-by-step task bookkeeping.
- Duplicates of an existing essence (search first: `uv run python -m mempalace search --mode hybrid "kw"`).
- Pure routine edits or refactors with no lesson.

## Proposal protocol
1. **Search** for an existing essence covering the candidate (avoid duplicates; decide new vs update).
2. **Classify** each candidate: `pitfall` | `preference` | `thinking_style`.
3. **Present** a compact block at the end of the reply:
   ```text
   🧠 MemPalace candidates (1)
   1. [pitfall] fastembed token truncation on long docs -> essence 2026-09-05-fastembed-truncation.md
   Reply "write 1" / "skip" / "edit" - nothing is written until you confirm.
   ```
4. "Skip - nothing worth remembering" is always a valid outcome.

## Write (only after user confirmation)
1. Create `MemPalace/essences/YYYY-MM-DD-slug.md` (English-only content; essence files are the single source of truth) or update existing file.
2. Sync the derived DB + search index:
   ```bash
   uv run python -m mempalace ingest
   ```
3. If dense/hybrid search is needed, run `uv run python -m mempalace embed`.

