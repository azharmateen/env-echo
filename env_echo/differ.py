"""Diff two .env files: show added/removed/changed variables."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .schema import parse_env_file


class DiffType(Enum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


@dataclass
class DiffEntry:
    """A single difference between two .env files."""
    diff_type: DiffType
    name: str
    value_a: Optional[str] = None
    value_b: Optional[str] = None
    security_relevant: bool = False


@dataclass
class DiffResult:
    """Result of diffing two .env files."""
    file_a: str
    file_b: str
    entries: List[DiffEntry] = field(default_factory=list)

    @property
    def added(self) -> List[DiffEntry]:
        return [e for e in self.entries if e.diff_type == DiffType.ADDED]

    @property
    def removed(self) -> List[DiffEntry]:
        return [e for e in self.entries if e.diff_type == DiffType.REMOVED]

    @property
    def changed(self) -> List[DiffEntry]:
        return [e for e in self.entries if e.diff_type == DiffType.CHANGED]

    @property
    def unchanged(self) -> List[DiffEntry]:
        return [e for e in self.entries if e.diff_type == DiffType.UNCHANGED]

    @property
    def has_differences(self) -> bool:
        return any(e.diff_type != DiffType.UNCHANGED for e in self.entries)


# Variable names that are security-relevant
SECURITY_NAMES = {
    "password", "secret", "token", "key", "api_key", "apikey",
    "private", "credential", "auth", "jwt", "oauth", "session",
    "encrypt", "salt", "hash",
}


def _is_security_relevant(name: str) -> bool:
    """Check if a variable name is security-relevant."""
    name_lower = name.lower()
    return any(s in name_lower for s in SECURITY_NAMES)


def diff_env_files(path_a: str, path_b: str,
                   show_values: bool = True) -> DiffResult:
    """Compare two .env files and produce a diff.

    Args:
        path_a: Path to first .env file.
        path_b: Path to second .env file.
        show_values: Include actual values in diff (False to redact secrets).

    Returns:
        DiffResult with all differences.
    """
    vars_a = parse_env_file(path_a)
    vars_b = parse_env_file(path_b)

    all_keys = sorted(set(list(vars_a.keys()) + list(vars_b.keys())))
    result = DiffResult(file_a=path_a, file_b=path_b)

    for key in all_keys:
        in_a = key in vars_a
        in_b = key in vars_b
        is_secret = _is_security_relevant(key)

        val_a = vars_a.get(key)
        val_b = vars_b.get(key)

        # Redact if needed
        display_a = val_a
        display_b = val_b
        if not show_values and is_secret:
            display_a = "***" if val_a else None
            display_b = "***" if val_b else None

        if in_a and not in_b:
            result.entries.append(DiffEntry(
                diff_type=DiffType.REMOVED,
                name=key,
                value_a=display_a,
                security_relevant=is_secret,
            ))
        elif not in_a and in_b:
            result.entries.append(DiffEntry(
                diff_type=DiffType.ADDED,
                name=key,
                value_b=display_b,
                security_relevant=is_secret,
            ))
        elif val_a != val_b:
            result.entries.append(DiffEntry(
                diff_type=DiffType.CHANGED,
                name=key,
                value_a=display_a,
                value_b=display_b,
                security_relevant=is_secret,
            ))
        else:
            result.entries.append(DiffEntry(
                diff_type=DiffType.UNCHANGED,
                name=key,
                value_a=display_a,
                value_b=display_b,
                security_relevant=is_secret,
            ))

    return result


def format_diff(result: DiffResult, show_unchanged: bool = False) -> str:
    """Format a diff result as a human-readable string."""
    lines = [
        f"Diff: {result.file_a} <-> {result.file_b}",
        "",
    ]

    if not result.has_differences:
        lines.append("No differences found.")
        return "\n".join(lines)

    # Summary
    lines.append(f"  Added:     {len(result.added)}")
    lines.append(f"  Removed:   {len(result.removed)}")
    lines.append(f"  Changed:   {len(result.changed)}")
    lines.append(f"  Unchanged: {len(result.unchanged)}")
    lines.append("")

    # Security warnings
    security_changes = [
        e for e in result.entries
        if e.security_relevant and e.diff_type != DiffType.UNCHANGED
    ]
    if security_changes:
        lines.append("SECURITY-RELEVANT CHANGES:")
        for entry in security_changes:
            lines.append(f"  ! {entry.diff_type.value.upper()}: {entry.name}")
        lines.append("")

    # Details
    for entry in result.entries:
        if entry.diff_type == DiffType.UNCHANGED and not show_unchanged:
            continue

        sec = " [SECURITY]" if entry.security_relevant else ""

        if entry.diff_type == DiffType.ADDED:
            lines.append(f"+ {entry.name}={entry.value_b or ''}{sec}")
        elif entry.diff_type == DiffType.REMOVED:
            lines.append(f"- {entry.name}={entry.value_a or ''}{sec}")
        elif entry.diff_type == DiffType.CHANGED:
            lines.append(f"~ {entry.name}{sec}")
            lines.append(f"    A: {entry.value_a}")
            lines.append(f"    B: {entry.value_b}")
        else:
            lines.append(f"  {entry.name}={entry.value_a or ''}")

    return "\n".join(lines)
