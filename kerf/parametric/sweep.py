"""Driving a parameter through a range and watching what breaks.

Every guide to parametric CAD gives the same advice. After writing your
equations, change each variable across the range you expect and check that
the model still rebuilds, because equations that work at the nominal value
often fail at the extremes. Nobody does it, because doing it by hand means
typing a number, waiting for a rebuild, and looking at the tree, over and
over.

Kerf can evaluate a part in a few milliseconds, so it can do that sweep and
report the range the model actually survives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .part import Part
from .validity import ModelIssue, check_part


@dataclass
class SweepPoint:
    value: float
    ok: bool
    volume: Optional[float] = None
    bodies: int = 0
    issues: list[ModelIssue] = field(default_factory=list)

    @property
    def reason(self) -> str:
        errors = [issue for issue in self.issues if issue.severity == "error"]
        return errors[0].describe() if errors else ""


@dataclass
class SweepResult:
    parameter: str
    nominal: Optional[float]
    points: list[SweepPoint] = field(default_factory=list)

    def failures(self) -> list[SweepPoint]:
        return [point for point in self.points if not point.ok]

    def warnings(self) -> list[SweepPoint]:
        """Values that build and come out looking wrong."""
        return [
            point for point in self.points
            if point.ok and any(issue.severity == "warning" for issue in point.issues)
        ]

    def working_range(self) -> Optional[tuple[float, float]]:
        """The unbroken span the part survives, around the value it shipped with.

        A part that fails in the middle of its own range and works at both
        ends is reported by the failure list rather than by this, because
        there is no single span to quote.
        """
        if not self.points or not any(point.ok for point in self.points):
            return None
        index = 0
        if self.nominal is not None:
            index = min(
                range(len(self.points)),
                key=lambda i: abs(self.points[i].value - self.nominal),
            )
        if not self.points[index].ok:
            return None
        low = high = index
        while low > 0 and self.points[low - 1].ok:
            low -= 1
        while high < len(self.points) - 1 and self.points[high + 1].ok:
            high += 1
        return self.points[low].value, self.points[high].value

    def volume_range(self) -> Optional[tuple[float, float]]:
        volumes = [p.volume for p in self.points if p.ok and p.volume is not None]
        return (min(volumes), max(volumes)) if volumes else None

    def robust(self) -> bool:
        return not self.failures()

    def summary(self) -> str:
        warned = self.warnings()
        note = ""
        if warned:
            first = warned[0]
            detail = next(
                (i.message for i in first.issues if i.severity == "warning"), "looks wrong"
            )
            note = f", and at {first.value:g} the part {detail}"
        if self.robust():
            span = f"{self.points[0].value:g} to {self.points[-1].value:g}"
            return f"{self.parameter} builds across {span}{note}"
        working = self.working_range()
        if working is None:
            return f"{self.parameter} fails at every value tried"
        return (
            f"{self.parameter} builds from {working[0]:g} to {working[1]:g}, "
            f"and {len(self.failures())} of {len(self.points)} values fail{note}"
        )

    def volume_bars(self, width: int = 24) -> list[str]:
        """A small bar per step, so the trend is visible in a terminal."""
        volumes = [p.volume or 0.0 for p in self.points]
        top = max(volumes) or 1.0
        rows = []
        for point, volume in zip(self.points, volumes):
            if not point.ok:
                rows.append(f"{point.value:>9.3g}  " + "x" * 3 + "  fails")
                continue
            filled = max(1, round(width * volume / top))
            rows.append(f"{point.value:>9.3g}  " + "#" * filled + f"  {volume:,.0f} mm3")
        return rows


def sweep_parameter(
    part: Part,
    name: str,
    start: float,
    stop: float,
    steps: int = 11,
    resolution: int = 28,
) -> SweepResult:
    """Set one parameter to each value in turn and check the part each time."""
    if name not in part.parameters:
        raise KeyError(f"{name} is not a parameter of this part")
    nominal = None
    original = part.parameters[name]
    if isinstance(original, (int, float)) and not isinstance(original, bool):
        nominal = float(original)

    steps = max(2, steps)
    result = SweepResult(parameter=name, nominal=nominal)
    for index in range(steps):
        value = start + (stop - start) * index / (steps - 1)
        trial = part.copy()
        trial.parameters[name] = value
        issues = check_part(trial, geometry=True, resolution=resolution)
        errors = [issue for issue in issues if issue.severity == "error"]
        volume = None
        bodies = 0
        if not errors:
            from .validity import measure_solid

            volume, bodies = measure_solid(trial, resolution)
        result.points.append(
            SweepPoint(value=value, ok=not errors, volume=volume, bodies=bodies, issues=issues)
        )
    return result


def default_range(value: float, spread: float = 0.6) -> tuple[float, float]:
    """A range to try when the caller did not name one.

    Dimensions are rarely useful at or below zero, so the low end stops just
    above it rather than crossing over.
    """
    magnitude = abs(value) or 1.0
    low = max(value - magnitude * spread, magnitude * 0.05)
    return low, value + magnitude * spread


def sweep_all(
    part: Part,
    spread: float = 0.6,
    steps: int = 7,
    resolution: int = 24,
) -> list[SweepResult]:
    """Sweep every parameter that holds a plain number.

    A parameter written as an expression is left alone, because replacing it
    with a number would delete the relationship its author wrote down.
    """
    results = []
    for name, raw in part.parameters.items():
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue
        low, high = default_range(float(raw), spread)
        results.append(sweep_parameter(part, name, low, high, steps, resolution))
    return results
