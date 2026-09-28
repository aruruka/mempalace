#!/usr/bin/env python3
# /// script
# description = "Invariant schema, qualification rubric, and ADR lifecycle validator for MemPalace."
# ///
"""Invariant schema, qualification rubric, and ADR lifecycle validator for MemPalace.

Validates:
1. Essence files (`MemPalace/essences/*.md`): valid category, valid lifecycle status,
   and non-empty content.
2. ADR files (`docs/decisions/ADR-*.md`): valid lifecycle status (`draft`, `proposed`,
   `active`, `accepted`, `rejected`, `deprecated`, `superseded`) and bidirectional
   `Supersedes:` / `Superseded-by:` link consistency.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from mempalace import ingest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
ESSENCES_DIR = WORKSPACE_ROOT / "MemPalace" / "essences"
DECISIONS_DIR = WORKSPACE_ROOT / "docs" / "decisions"

VALID_ESSENCE_CATEGORIES = {"preference", "pitfall", "thinking_style"}
VALID_ESSENCE_STATUSES = {"active", "accepted", "superseded", "deprecated", "archived"}
VALID_ADR_STATUSES = {
    "draft",
    "proposed",
    "active",
    "accepted",
    "rejected",
    "deprecated",
    "superseded",
}

_STATUS_LINE_RE = re.compile(r"^\s*(?:\*\*Status\*\*|Status)\s*:\s*([A-Za-z_-]+)", re.M | re.I)
_SUPERSEDES_RE = re.compile(r"^\s*(?:\*\*Supersedes\*\*|Supersedes)\s*:\s*(.+)$", re.M | re.I)
_SUPERSEDED_BY_RE = re.compile(
    r"^\s*(?:\*\*Superseded[- ]by\*\*|Superseded[- ]by)\s*:\s*(.+)$", re.M | re.I
)
_ADR_ID_RE = re.compile(r"ADR-\d{3}")


def _extract_adr_refs(text: str, pattern: re.Pattern[str]) -> list[str]:
    match = pattern.search(text)
    if not match:
        return []
    raw = match.group(1).strip()
    if raw.lower() in {"none", "n/a", "-", ""}:
        return []
    return _ADR_ID_RE.findall(raw.upper())


def _extract_adr_status(text: str) -> str:
    match = _STATUS_LINE_RE.search(text)
    if not match:
        return "active"
    return match.group(1).strip().lower()


def validate_essences(essences_dir: Path = ESSENCES_DIR) -> list[str]:
    """Validate essence files in MemPalace/essences/."""
    errors: list[str] = []
    if not essences_dir.exists():
        return [f"Essences directory not found: {essences_dir}"]

    for path in sorted(essences_dir.glob("*.md")):
        if path.name.lower() in {"readme.md", "template.md"}:
            continue
        rec = ingest.parse_essence(path)
        if rec.category is not None and rec.category not in VALID_ESSENCE_CATEGORIES:
            errors.append(
                f"[Essence] Invalid category '{rec.category}' in {path.name}. "
                f"Expected one of {sorted(VALID_ESSENCE_CATEGORIES)}"
            )
        if rec.status not in VALID_ESSENCE_STATUSES:
            errors.append(
                f"[Essence] Invalid status '{rec.status}' in {path.name}. "
                f"Expected one of {sorted(VALID_ESSENCE_STATUSES)}"
            )
        if not rec.content.strip():
            errors.append(f"[Essence] Empty content in {path.name}")
    return errors


def validate_adrs(decisions_dir: Path = DECISIONS_DIR) -> list[str]:
    """Validate ADR files and bidirectional supersession links in docs/decisions/."""
    errors: list[str] = []
    if not decisions_dir.exists():
        return [f"Decisions directory not found: {decisions_dir}"]

    records: dict[str, tuple[Path, str, str]] = {}
    for path in sorted(decisions_dir.glob("ADR-*.md")):
        match = ingest.ADR_FILE_RE.match(path.name)
        if not match:
            errors.append(f"[ADR] Invalid filename pattern: {path.name}")
            continue
        adr_id = match.group(1).upper()
        raw = path.read_text(encoding="utf-8")
        status = _extract_adr_status(raw)
        records[adr_id] = (path, status, raw)
        if status not in VALID_ADR_STATUSES:
            errors.append(
                f"[ADR] Invalid status '{status}' in {path.name}. "
                f"Expected one of {sorted(VALID_ADR_STATUSES)}"
            )

    for adr_id, (path, status, raw) in records.items():
        supersedes = _extract_adr_refs(raw, _SUPERSEDES_RE)
        superseded_by = _extract_adr_refs(raw, _SUPERSEDED_BY_RE)

        for target_id in supersedes:
            if target_id not in records:
                errors.append(
                    f"[ADR] {path.name} claims to supersede {target_id}, "
                    f"but {target_id} does not exist"
                )
                continue
            target_path, target_status, target_raw = records[target_id]
            if target_status != "superseded":
                errors.append(
                    f"[ADR] {target_path.name} is superseded by {adr_id}, "
                    f"but its Status is '{target_status}' (expected 'superseded')"
                )
            target_sup_by = _extract_adr_refs(target_raw, _SUPERSEDED_BY_RE)
            if adr_id not in target_sup_by:
                errors.append(
                    f"[ADR] {target_path.name} is superseded by {adr_id}, "
                    f"but is missing 'Superseded-by: {adr_id}' header"
                )

        if status == "superseded":
            if not superseded_by:
                errors.append(
                    f"[ADR] {path.name} has Status: superseded, "
                    f"but is missing 'Superseded-by: ADR-NNN' header"
                )
            for by_id in superseded_by:
                if by_id not in records:
                    errors.append(
                        f"[ADR] {path.name} is superseded by non-existent record '{by_id}'"
                    )

    return errors


def main() -> int:
    """Run governance validation across essences and ADRs."""
    print("=== MemPalace Governance & Lifecycle Verification ===")
    all_errors = validate_essences() + validate_adrs()
    if all_errors:
        print(f"\n[FAIL] Validation failed with {len(all_errors)} error(s):")
        for err in all_errors:
            print(f"  - {err}")
        return 1
    print("\n[OK] All essences and ADRs passed schema and lifecycle validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
