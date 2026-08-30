"""Checking whether a clean merge produced a part that makes sense.

A three way merge on feature ids can succeed while the result is physically
wrong, because two people can add features that occupy the same space without
either edit touching the other's fields. This check re-evaluates the merged
part and looks for that overlap. It is the reason automatic merging is safe
enough to offer at all.
"""

from __future__ import annotations

import numpy as np

from ..parametric import Part, feature_bounds, feature_sdf
from .conflicts import Conflict


def detect_interference(
    path: str,
    merged: Part,
    ours_added: list[str],
    theirs_added: list[str],
    samples: int = 24,
) -> list[Conflict]:
    """Report pairs of newly added features that share space.

    Only features added on opposite sides are compared. Anything that was
    already in the common ancestor was agreed on before the branches split.
    """
    if not ours_added or not theirs_added:
        return []
    try:
        params = merged.resolved_parameters()
    except Exception:                                # noqa: BLE001
        return []

    found: list[Conflict] = []
    for our_id in ours_added:
        ours = merged.feature(our_id)
        if ours is None or ours.suppressed:
            continue
        for their_id in theirs_added:
            theirs = merged.feature(their_id)
            if theirs is None or theirs.suppressed:
                continue

            our_low, our_high = feature_bounds(ours, params)
            their_low, their_high = feature_bounds(theirs, params)
            low = np.maximum(our_low, their_low)
            high = np.minimum(our_high, their_high)
            if np.any(high <= low):
                continue

            axes = [np.linspace(low[i], high[i], samples) for i in range(3)]
            points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1)
            overlap = (feature_sdf(ours, points, params) < 0) & (
                feature_sdf(theirs, points, params) < 0
            )
            if not overlap.any():
                continue

            cell = float(np.prod((high - low) / (samples - 1)))
            volume = float(overlap.sum()) * cell
            span = high - low
            if volume < 1e-9 or volume < 1e-4 * float(np.prod(np.maximum(span, 1e-9))):
                continue

            ops = (ours.op, theirs.op)
            if ops == ("subtract", "subtract"):
                detail = (
                    f"both branches cut material here, and the two pockets break into "
                    f"one another over {volume:.3g} mm^3"
                )
            elif "subtract" in ops:
                cut, solid = (theirs, ours) if theirs.op == "subtract" else (ours, theirs)
                detail = (
                    f"{cut.label()} cuts {volume:.3g} mm^3 out of {solid.label()}, "
                    f"which was added on the other branch"
                )
            else:
                detail = (
                    f"two bodies added independently occupy the same "
                    f"{volume:.3g} mm^3 of space"
                )
            found.append(
                Conflict(path, "interference", f"{ours.label()} / {theirs.label()}", detail=detail)
            )
    return found
