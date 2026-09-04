# ADR-009: SQLite Hybrid Retrieval for MemPalace v2

Date: 2026-09-03
Status: active
Tags: memory, retrieval, sqlite, fts5, embeddings, hybrid

## Context
MemPalace v1 (ADR-002: DuckDB storage) ships ILIKE-only substring search: no ranking, no
tokenization or stemming, OR-union semantics, wildcard-injection hazards, unbounded output, and an
undetectable dual-write drift between `MemPalace/essences/*.md` and DB rows (benchmark probes
2026-09-02: `file lock` missed the actual pitfall; `vmmem wslconfig` returned zero wisdom hits;
`convert html to pdf without a browser` flooded 27 wisdom / 75 session rows). A golden recall
benchmark (28 queries over the real essence corpus) was built to gate any replacement.

## Decision
Rebuild MemPalace as a **full-Python, three-layer hybrid retrieval engine** (`src/mempalace/`, Typer
CLI), superseding the DuckDB storage decision:

1. **Storage**: stdlib SQLite (`MemPalace/memory.sqlite`) with FTS5 (porter tokenizer) for the
   lexical layer; sessions/tool_registry migrated once from the legacy DuckDB file (which is kept,
   never deleted, until parity is confirmed).
2. **Single source of truth**: wisdom and decision rows are **derived from files** (essence `.md`
   and ADR `.md`) by `ingest`; `reconcile` reports drift in both directions plus the historical v1
   gap. This eliminates v1's dual-write flaw by construction.
3. **Retrieval layers**: L1 = FTS5 BM25 (AND semantics, stopword filtering, injection-safe quoted
   phrases, ranked-OR fallback); L2 = dense cosine over `BAAI/bge-small-en-v1.5` embeddings via
   fastembed (numpy brute-force — no ANN needed at this scale; sqlite-vec is the documented upgrade
   path); L3 = Reciprocal Rank Fusion (k=60). Embedding failures degrade gracefully to BM25.
4. **Quality gates**: golden benchmark (core Q01–Q20) macro recall@5 ≥ 0.85 — measured 1.000 in
   hybrid mode, 0.925 BM25-only; BDD contract (pytest-bdd), in-memory pytest, and black-box
   subprocess tests (268 passing); ruff + pyright strict clean.

## Alternatives Considered
- Keeping DuckDB + `fts`/`vss` extensions: rejected — DuckDB's columnar strength is irrelevant at
  this scale, extensions add load/version friction, and v1's drift design would remain.
- External memory platforms (mem0/Zep/Letta/basic-memory) and vector-DB servers: rejected — wrong
  category for a ~150-record single-user CLI memory; LLM-dependent write paths and opaque stores
  repeat the v1 failure modes.
- Go implementation (Go CLI + Python embeddings): rejected — `CGO_ENABLED=0`, no C toolchain, uv-only
  workspace rules, and no performance/distribution need at this corpus size.
- sqlite-vec now: deferred — documented upgrade path; brute-force cosine is sub-millisecond at this
  scale.

## Consequences
- Positive: ranked, semantic, hybrid retrieval (benchmark 1.000 recall@5); deterministic file-derived
  DB with zero drift by construction; one-language (Python/uv) codebase with black-box CLI contract.
- Positive: legacy `scripts/` and `MemPalace/memory.duckdb` remain untouched for reference/migration.
- Tradeoff: model download (~130 MB) needed once for dense/hybrid; Chinese cross-language queries
  (benchmark probes Q23/Q24) and typo tolerance (Q22) remain stretch goals — `bge-small-en-v1.5` is
  English-centric.
- Tradeoff: schema migrations now handled in code (`init_db`), mirroring the v1 pattern.

## Supersedes
ADR-002 (DuckDB storage for MemPalace).

## Supersession
None.
