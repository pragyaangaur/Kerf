"""The .kpart file: a parameter table and an ordered list of features.

A mesh records what a part looks like. A feature tree records why it looks
that way, and that is the difference version control needs. A mesh cannot
tell you that a hole grew by 2 mm, and it cannot be merged with somebody
else's copy. A feature tree can do both.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..geometry.mesh import Mesh
from .expr import ExpressionError, resolve
from .features import Feature
from .sdf import feature_bounds, feature_sdf, smooth_intersect, smooth_subtract, smooth_union
from .tessellate import surface_nets


@dataclass
class Part:
    name: str = "part"
    units: str = "mm"
    parameters: dict[str, Any] = field(default_factory=dict)
    features: list[Feature] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def loads(data: bytes | str) -> "Part":
        raw = json.loads(data.decode() if isinstance(data, bytes) else data)
        if "kerf_part" not in raw:
            raise ValueError("not a kerf part file (missing 'kerf_part')")
        part = Part(
            name=raw.get("name", "part"),
            units=raw.get("units", "mm"),
            parameters=dict(raw.get("parameters", {})),
            features=[Feature.from_dict(item) for item in raw.get("features", [])],
            meta=dict(raw.get("meta", {})),
        )
        seen: set[str] = set()
        for item in part.features:
            if item.id in seen:
                raise ValueError(f"duplicate feature id {item.id!r}")
            seen.add(item.id)
        return part

    def dumps(self) -> bytes:
        document = {
            "kerf_part": 1,
            "name": self.name,
            "units": self.units,
            "parameters": self.parameters,
            "features": [item.to_dict() for item in self.features],
        }
        if self.meta:
            document["meta"] = self.meta
        return (json.dumps(document, indent=2) + "\n").encode()

    def copy(self) -> "Part":
        return Part.loads(self.dumps())

    def feature(self, feature_id: str) -> Feature | None:
        return next((item for item in self.features if item.id == feature_id), None)

    def resolved_parameters(self) -> dict[str, float]:
        """Turn the parameter table into numbers.

        Parameters may refer to each other, so this repeats until everything
        resolves. A parameter that never resolves is either circular or points
        at a name that does not exist, and both are reported.
        """
        resolved: dict[str, float] = {}
        pending = dict(self.parameters)
        for _ in range(len(pending) + 1):
            if not pending:
                break
            progressed = False
            for key in list(pending):
                try:
                    resolved[key] = resolve(pending[key], resolved)
                except ExpressionError:
                    continue
                del pending[key]
                progressed = True
            if not progressed:
                break
        if pending:
            raise ExpressionError(
                "unresolvable parameters (circular or undefined): "
                + ", ".join(sorted(pending))
            )
        return resolved

    def active_features(self) -> list[Feature]:
        return [item for item in self.features if not item.suppressed]

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """A box containing the part. Only features that add material count,
        because a subtraction can reach far outside the solid it cuts."""
        params = self.resolved_parameters()
        boxes = [
            feature_bounds(item, params)
            for item in self.active_features()
            if item.op != "subtract"
        ]
        if not boxes:
            return np.array([-1.0, -1.0, -1.0]), np.array([1.0, 1.0, 1.0])
        low = np.min([box[0] for box in boxes], axis=0)
        high = np.max([box[1] for box in boxes], axis=0)
        pad = max(float((high - low).max()) * 0.05, 1e-6)
        return low - pad, high + pad

    def sdf(self, points: np.ndarray) -> np.ndarray:
        """Fold the feature list into one distance field, in order."""
        params = self.resolved_parameters()
        shape = points.shape[:-1]
        field_values = np.full(shape, 1e9)
        started = False
        for item in self.active_features():
            values = feature_sdf(item, points, params)
            blend = float(resolve(item.params.get("blend", 0), params))
            if not started:
                # A part that begins with a cut has nothing to cut into yet.
                if item.op == "subtract":
                    continue
                field_values = values
                started = True
            elif item.op == "add":
                field_values = smooth_union(field_values, values, blend)
            elif item.op == "subtract":
                field_values = smooth_subtract(field_values, values, blend)
            else:
                field_values = smooth_intersect(field_values, values, blend)
        return field_values

    def evaluate(self, resolution: int = 64) -> Mesh:
        """Sample the field on a lattice and turn it into triangles."""
        low, high = self.bounds()
        span = high - low
        pitch = float(span.max()) / max(resolution, 4)
        dims = tuple(int(max(2, math.ceil(size / pitch))) + 1 for size in span)
        axes = [low[i] + np.arange(dims[i]) * pitch for i in range(3)]
        points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1)
        return surface_nets(self.sdf(points), low, pitch)

    def geometry_summary(self, resolution: int = 48) -> dict:
        stats = self.evaluate(resolution).stats()
        stats["features"] = len(self.features)
        stats["active_features"] = len(self.active_features())
        stats["parameters"] = len(self.parameters)
        return stats
