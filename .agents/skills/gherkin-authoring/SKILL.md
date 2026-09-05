---
name: gherkin-authoring
description: Gherkin acceptance criteria and BDD feature authoring for MemPalace pytest-bdd contract tests.
tags:
  - bdd
  - gherkin
  - testing
  - pytest-bdd
---

# Gherkin Authoring for MemPalace

Gherkin/BDD acceptance criteria authoring for executable specifications and contract testing in MemPalace using `pytest-bdd`.

## When to Use This Skill
- Adding or updating executable acceptance criteria in `tests/features/*.feature`.
- Implementing or binding step definitions in `tests/test_bdd_contract.py`.
- Formulating acceptance criteria for A2A Task Objects in Given/When/Then structure.

## Feature File Structure

```gherkin
Feature: <Feature Name>
  As an <actor/agent>
  I want <capability/behavior>
  So that <business value/benefit>

  Scenario: <Scenario Name>
    Given <precondition>
    When <action>
    Then <expected outcome>
    And <additional assertion>
```

## Step Conventions in MemPalace

- **Given**: Workspace state (e.g. `Given a fresh workspace database is initialized`, `Given a workspace ingested into the database`).
- **When**: CLI or API action (e.g. `When the CLI ingests the workspace`, `When I search in bm25 mode for "<query>"`).
- **Then**: Assertions on DB rows, drift reports, or search ranking (e.g. `Then the database has one wisdom row per essence file`, `Then the command prints valid JSON with a hits array`).

## Binding Steps with pytest-bdd
Step implementations reside in `tests/test_bdd_contract.py`:

```python
from pytest_bdd import given, when, then, parsers, scenarios

scenarios("features/mempalace.feature")


@given("a fresh workspace database is initialized")
def fresh_db(tmp_path: Path): ...
```

## Verification
Validate all BDD scenarios with:
```bash
uv run pytest tests/test_bdd_contract.py
```

