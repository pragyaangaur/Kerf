"""Whether a part can be built at all.

CAD calls this a rebuild error. A dimension points at a variable somebody
deleted, two equations refer to each other in a loop, or a value goes to zero
and a feature collapses. The model stops regenerating, and the person who
finds out is usually not the person who caused it.

These checks answer the same question without opening a CAD system, which is
what lets kerf run them on a merge before the merge is allowed to land.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..geometry.voxels import label_regions
from .expr import ExpressionError, resolve
from .graph import build_graph

# Fields that describe a size. A size of zero or less collapses the feature.
POSITIVE_KEYS = {"radius", "height", "tube"}


@dataclass
class ModelIssue:
    severity: str        # error or warning
    scope: str           # equation, feature, or geometry
    where: str
    message: str

    def describe(self) -> str:
        return f"{self.where}: {self.message}"


def check_equations(part) -> list[ModelIssue]:
    """Check the equations on their own, without building any geometry."""
    issues: list[ModelIssue] = []
    graph = build_graph(part)

    for where, missing in graph.dangling():
        issues.append(
            ModelIssue(
                "error", "equation", where,
                f"reads {missing!r}, which the parameter table does not define",
            )
        )

    for loop in graph.cycles():
        issues.append(
            ModelIssue(
                "error", "equation", " -> ".join(loop),
                "these parameters depend on each other in a loop",
            )
        )

    if issues:
        return issues                       # values cannot be trusted yet

    try:
        values = part.resolved_parameters()
    except ExpressionError as error:
        return [ModelIssue("error", "equation", "parameters", str(error))]

    for name, value in values.items():
        if not math.isfinite(value):
            issues.append(
                ModelIssue("error", "equation", name, f"resolves to {value}")
            )
    return issues


def check_features(part, values: dict[str, float]) -> list[ModelIssue]:
    """Check that every feature has dimensions it can be built from."""
    issues: list[ModelIssue] = []
    for feature in part.active_features():
        for key, raw in feature.params.items():
            if key in POSITIVE_KEYS:
                number = _number(raw, values)
                if number is not None and number <= 0:
                    issues.append(
                        ModelIssue(
                            "error", "feature", f"{feature.label()}.{key}",
                            f"is {number:g}, and a size has to be above zero",
                        )
                    )
            elif key == "size":
                for index, item in enumerate(raw if isinstance(raw, (list, tuple)) else []):
                    number = _number(item, values)
                    if number is not None and number <= 0:
                        axis = "xyz"[index] if index < 3 else str(index)
                        issues.append(
                            ModelIssue(
                                "error", "feature", f"{feature.label()}.size.{axis}",
                                f"is {number:g}, and a size has to be above zero",
                            )
                        )
    return issues


def _number(raw, values: dict[str, float]):
    try:
        return resolve(raw, values)
    except Exception:                        # noqa: BLE001
        return None


def measure_solid(part, resolution: int = 32) -> tuple[float, int]:
    """Volume and body count, taken from the field without tessellating.

    A sweep evaluates a part many times over, and the mesh is not needed to
    answer whether the part still exists and whether it is still in one piece.

    Counting cells whose centre is inside would be simpler and it aliases
    badly, because a flat face lying near a layer of centres flips that whole
    layer in or out. The distance itself says how far through the cell the
    surface passes, so each cell contributes the fraction it actually fills.
    """
    low, high = part.bounds()
    span = high - low
    pitch = float(span.max()) / max(resolution, 4)
    dims = tuple(int(max(2, math.ceil(size / pitch))) for size in span)
    axes = [low[i] + (np.arange(dims[i]) + 0.5) * pitch for i in range(3)]
    points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1)
    distance = part.sdf(points)
    filled = np.clip(0.5 - distance / pitch, 0.0, 1.0)
    volume = float(filled.sum()) * pitch ** 3
    inside = distance < 0
    if not inside.any():
        return 0.0, 0
    _, bodies = label_regions(inside)
    return volume, bodies


def inspect_part(
    part, resolution: int = 32
) -> tuple[list[ModelIssue], Optional[float], int]:
    """Every check, plus the measurements the geometry check already took.

    A sweep asks the same question a few dozen times over, and the volume it
    wants to chart is a by-product of the check it has just run. Handing it
    back costs nothing and halves the work.
    """
    issues = check_equations(part)
    if issues:
        return issues, None, 0

    values = part.resolved_parameters()
    issues.extend(check_features(part, values))
    if issues:
        return issues, None, 0

    if not part.active_features():
        return [ModelIssue("error", "geometry", "part", "has no features left to build")], None, 0

    try:
        volume, bodies = measure_solid(part, resolution)
    except Exception as error:               # noqa: BLE001
        return (
            [ModelIssue("error", "geometry", "part", f"cannot be evaluated: {error}")],
            None,
            0,
        )

    if volume <= 0:
        issues.append(
            ModelIssue("error", "geometry", "part", "builds to nothing at this size")
        )
        return issues, volume, bodies
    if bodies > 1:
        issues.append(
            ModelIssue(
                "warning", "geometry", "part",
                f"has fallen into {bodies} separate bodies",
            )
        )
    return issues, volume, bodies


def check_part(part, geometry: bool = True, resolution: int = 32) -> list[ModelIssue]:
    """Every check, in the order that makes the first failure the useful one."""
    if not geometry:
        issues = check_equations(part)
        if issues:
            return issues
        return check_features(part, part.resolved_parameters())
    return inspect_part(part, resolution)[0]


def is_buildable(part, resolution: int = 32) -> bool:
    return not any(issue.severity == "error" for issue in check_part(part, True, resolution))
