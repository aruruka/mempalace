# ADR-002: DuckDB for MemPalace Storage

Date: 2026-04-16
Status: superseded
Tags: memory, storage, duckdb

## Context
The workspace needs local, structured, queryable memory for sessions, pitfalls, preferences, and tool metadata.

## Decision
Use DuckDB as the persistent storage engine for MemPalace at `MemPalace/memory.duckdb`.

## Alternatives Considered
1. SQLite.
2. External vector database.
3. Markdown-only notes without structured DB.

## Consequences
- Positive: simple local deployment and strong SQL support for structured retrieval.
- Positive: easy integration with Python scripts and append-style logging.
- Tradeoff: schema migrations must be handled explicitly in scripts.

## Supersession
Superseded by ADR-009 (SQLite hybrid retrieval for MemPalace v2, 2026-09-03). The DuckDB file
`MemPalace/memory.duckdb` is retained for reference/migration, not as the active store.
