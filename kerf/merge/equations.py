"""Checking that a merged part still has equations that resolve.

This is the second validity gate, and it catches a failure neither side can
see on its own. One person renames a parameter, the other person writes a new
dimension that reads the old name, and both branches build. Merge them and
the part will not rebuild, because the name each half assumed is no longer
the name the other half provides.

Only issues the merge itself introduced are reported. A part that was already
broken before anybody touched it is not this merge's fault.
"""

from __future__ import annotations

from ..parametric import Part
from ..parametric.validity import ModelIssue, check_equations
from .conflicts import Conflict


def _signature(issue: ModelIssue) -> tuple[str, str, str]:
    return issue.severity, issue.where, issue.message


def introduced_issues(
    merged: Part, sides: list[Part | None]
) -> list[ModelIssue]:
    """Equation problems in the merged part that no input part already had."""
    existing = set()
    for side in sides:
        if side is None:
            continue
        for issue in check_equations(side):
            existing.add(_signature(issue))
    return [
        issue for issue in check_equations(merged)
        if _signature(issue) not in existing
    ]


def detect_equation_breaks(
    path: str, merged: Part, base: Part | None, ours: Part, theirs: Part
) -> list[Conflict]:
    """Report equations the merge broke, as conflicts."""
    conflicts: list[Conflict] = []
    for issue in introduced_issues(merged, [base, ours, theirs]):
        if issue.severity != "error":
            continue
        conflicts.append(
            Conflict(
                path, "equation", issue.where,
                detail=(
                    f"{issue.message}. Both branches build on their own, and the "
                    f"merged part would not rebuild."
                ),
            )
        )
    return conflicts
