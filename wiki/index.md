---
type: Catalog
title: MemPalace Wiki Index
description: Content catalog and cross-reference index of MemPalace persistent knowledge.
resource: file:///D:/Work/mempalace/wiki/index.md
tags: [catalog, index, okf-v0.2, wiki]
status: active
generated:
  actor: agent:antigravity/1.0
  timestamp: 2026-09-05T22:05:00Z
sources:
  - id: agy-agents-spec
    resource: file:///D:/Work/mempalace/AGENTS.md
    title: AGENTS.md Operating Rules
    author: agent:antigravity
    usage_count: 1
    last_modified: 2026-09-05
verified:
  by: agent:antigravity/1.0
  at: 2026-09-05T22:05:00Z
  method: inspection
---

# MemPalace Persistent Knowledge Index

> **Standards Compliance**: Google Cloud Open Knowledge Format (OKF v0.2) + Karpathy LLM Wiki Architecture.

Welcome to the MemPalace persistent knowledge base. This wiki serves as the Layer 2 compiled knowledge store for coding agents working within the MemPalace codebase.

---

## 1. Architecture & Engine

- [MemPalace v2 — SQLite Hybrid Retrieval Memory](file:///D:/Work/mempalace/wiki/mempalace-v2-hybrid-retrieval.md)  
  *Tags*: `[memory, retrieval, sqlite, fts5, embeddings, hybrid, mempalace, typer]`  
  *Summary*: Full-Python hybrid retrieval engine replacing DuckDB v1 with SQLite FTS5 (BM25), fastembed dense embeddings, and Reciprocal Rank Fusion (RRF).

---

## 2. Playbooks & Protocols

- [Harness Engineering Pattern](file:///D:/Work/mempalace/docs/harness-playbook/PATTERN.md)  
  *Tags*: `[a2a-protocol, harness, pattern]`  
  *Summary*: Agent2Agent Client/Remote collaboration workflow and state transitions.

- [Architect Checklist](file:///D:/Work/mempalace/docs/harness-playbook/architect-checklist.md)  
  *Tags*: `[a2a-protocol, quality-gate, architect]`  
  *Summary*: Pre-dispatch checklist for A2A Task Objects.

- [Implementor Handoff Template](file:///D:/Work/mempalace/docs/harness-playbook/implementor-handoff-template.md)  
  *Tags*: `[a2a-protocol, task-object, template]`  
  *Summary*: Multi-part task handoff template.

---

## 3. Maintenance & Audit

- [Audit Log (`wiki/log.md`)](file:///D:/Work/mempalace/wiki/log.md): Append-only chronological audit trail of all knowledge syntheses.

