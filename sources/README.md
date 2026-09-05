# Layer 1: Immutable Raw Sources

This directory contains immutable ground-truth sources:
- Benchmark logs and raw test dumps
- Upstream protocol specs and RFC references
- Historical schema exports

## Operational Rules
- **Agents MUST NEVER edit files in `sources/`**.
- New sources are added as read-only references.
- Synthesize knowledge into `wiki/` concepts rather than modifying sources.

