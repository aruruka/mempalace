Feature: MemPalace hybrid retrieval CLI
  As an agent using MemPalace v2
  I want the CLI to initialize, ingest, search and reconcile
  So that retrieval is ranked, deterministic and drift-free

  Scenario: Initialize an empty database
    Given a fresh workspace database is initialized
    Then the database contains the v1-mirror tables and an FTS index

  Scenario: Ingest builds the database from source files
    Given a workspace with essence files and an ADR file
    When the CLI ingests the workspace
    Then the database has one wisdom row per essence file
    And the database has one decision row per ADR file
    And the search index is populated

  Scenario: BM25 search ranks the file-locking pitfall for a natural-language query
    Given a workspace ingested into the database
    When I search in bm25 mode for "file lock when updating hermes agent on windows"
    Then the top hit references the hermes file-locking essence

  Scenario: Multi-keyword search uses AND semantics
    Given a workspace ingested into the database
    When I search in bm25 mode for "uv cache rename"
    Then every hit references the uv cache rename essence
    And the hit count is one

  Scenario: Reconcile reports zero drift after ingest
    Given a workspace ingested into the database
    When I run reconcile
    Then the drift report lists no files without rows and no rows without files

  Scenario: Search prints valid JSON
    Given a workspace ingested into the database
    When I search in bm25 mode for "duckdb"
    Then the command prints valid JSON with a hits array

  Scenario: Ingest is idempotent
    Given a workspace ingested into the database
    When the CLI ingests the workspace again
    Then the wisdom and decision counts are unchanged
