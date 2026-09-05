# MemPalace Essences

Essence files (`*.md`) are the **single source of truth** for long-term agent memory.
Each essence represents a hard-won pitfall, architectural preference, or thinking style.

## Rules
- **English-only**: Workspace policy requires English text.
- **Derived SQLite store**: The database (`MemPalace/memory.sqlite`) is derived from these files via:
  ```bash
  uv run python -m mempalace ingest
  ```
- **Syncing memory**: Run `mempalace ingest` after creating or editing essence files.

