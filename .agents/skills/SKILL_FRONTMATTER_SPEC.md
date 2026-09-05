# Skill Frontmatter Specification

This workspace standardizes skill metadata using YAML frontmatter at the top of every `SKILL.md`.

## Required Structure
Each skill file must begin with:

```yaml
---
name: <kebab-case-unique-skill-name>
description: <one-line-purpose>
tags:
  - <tag-1>
  - <tag-2>
---
```

## Required Fields
- `name`: unique, stable, kebab-case identifier (for example: `decision-making`).
- `description`: concise one-line summary of the skill.
- `tags`: non-empty list for discovery/routing.

## Formatting Rules
- Frontmatter must be the first content in file (no leading text).
- Use lowercase kebab-case for `name`.
- Keep `description` plain text, one sentence.
- Keep tags lowercase and short.

## Compatibility Note
This format is intentionally minimal and portable across common agent ecosystems (OpenAI, Anthropic, and Google toolchains) that support YAML-frontmatter style metadata extraction.

