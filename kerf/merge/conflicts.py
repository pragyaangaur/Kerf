"""The shapes a merge result can take."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def short(value: Any) -> str:
    """Trim a value down to something that fits on one line of output."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    text = str(value)
    return text if len(text) <= 32 else text[:29] + "..."


@dataclass
class Conflict:
    path: str
    scope: str          # parameter, feature, field, order, file, interference
    key: str
    base: Any = None
    ours: Any = None
    theirs: Any = None
    detail: str = ""

    def describe(self) -> str:
        if self.scope in ("interference", "file"):
            return f"{self.key}: {self.detail}"
        return (
            f"{self.scope} {self.key}: ours={short(self.ours)} "
            f"theirs={short(self.theirs)} (base={short(self.base)})"
        )


@dataclass
class FileMerge:
    path: str
    status: str          # merged, ours, theirs, unchanged, conflict, added, removed
    data: Optional[bytes] = None
    conflicts: list[Conflict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ours_data: Optional[bytes] = None
    theirs_data: Optional[bytes] = None


@dataclass
class MergeResult:
    files: list[FileMerge] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.conflicts
