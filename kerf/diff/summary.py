"""Turning a diff into one line a person can read."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:                                    # pragma: no cover
    from .models import ModelDiff


def human_volume(value: float, units: str = "mm", ascii_only: bool = False) -> str:
    """Format a volume in the unit a machinist would say out loud."""
    cube = "^3" if ascii_only else "³"
    if units != "mm":
        return f"{value:.3g}"
    if abs(value) >= 1e6:
        return f"{value / 1e3:,.0f} cm{cube}"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.2f} cm{cube}"
    return f"{value:.3g} mm{cube}"


def summarize(diff: "ModelDiff") -> str:
    """One line describing what happened to a file."""
    if diff.status == "added":
        triangles = diff.new_stats.get("triangles")
        return "new part" + (f", {triangles} triangles" if triangles else "")
    if diff.status == "removed":
        return "deleted"
    if diff.status == "reexported":
        return "re-exported, geometry identical"
    if diff.status == "rewritten":
        text = "feature tree edited, same solid"
        if diff.parametric and not diff.parametric.empty():
            counts: dict[str, int] = {}
            for change in diff.parametric.features:
                counts[change.status] = counts.get(change.status, 0) + 1
            if counts:
                text += " (" + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) + ")"
        return text
    if diff.status.startswith("renamed") and "modified" not in diff.status:
        return f"renamed from {diff.old_path}"

    parts: list[str] = []
    if diff.parametric and not diff.parametric.empty():
        tree = diff.parametric
        if tree.parameters:
            parts.append(", ".join(change.describe() for change in tree.parameters[:2]))
        counts: dict[str, int] = {}
        for change in tree.features:
            counts[change.status] = counts.get(change.status, 0) + 1
        if counts:
            parts.append(", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
    if diff.volume and not diff.volume.unchanged:
        volume = diff.volume
        if volume.translation:
            distance = float(np.linalg.norm(volume.translation))
            parts.append(f"body moved {distance:.2g} mm")
        else:
            pieces = []
            if volume.added_volume > 0:
                pieces.append(f"+{human_volume(volume.added_volume)}")
            if volume.removed_volume > 0:
                pieces.append(f"-{human_volume(volume.removed_volume)}")
            if pieces:
                parts.append(
                    " / ".join(pieces) + f" ({volume.changed_fraction * 100:.1f}% of body)"
                )
    if not parts:
        for metric in diff.metrics:
            if metric.key == "volume":
                parts.append(
                    f"volume {metric.pct:+.1f}%" if metric.pct is not None else "volume changed"
                )
    return "; ".join(parts) if parts else (diff.note or "changed")
