"""Feature geometry as signed distance fields.

Every feature is a function that returns the distance from a point to its
surface, negative inside. Combining features is then arithmetic on those
distances, and a fillet is a smooth version of the same arithmetic. This is
what lets a part file describe real geometry without a solid modelling
kernel behind it.
"""

from __future__ import annotations

import math

import numpy as np

from .expr import resolve, resolve_vec
from .features import Feature


def feature_bounds(feature: Feature, params: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    """A box that contains the feature, used to size the sampling lattice.

    A rotated feature needs the box around the rotated shape, not around the
    shape it started as. Getting that wrong makes the lattice too small, and
    the part is then quietly cut off at the edge of its own sampling volume.
    """
    centre = resolve_vec(feature.params.get("center"), params)
    if feature.type == "box":
        half = resolve_vec(feature.params.get("size"), params, (1, 1, 1)) / 2.0
    elif feature.type == "cylinder":
        radius = resolve(feature.params.get("radius", 1), params)
        half_height = resolve(feature.params.get("height", 1), params) / 2.0
        axis = str(feature.params.get("axis", "z")).lower()
        half = np.array([radius, radius, radius], dtype=float)
        half["xyz".index(axis)] = half_height
    elif feature.type == "sphere":
        radius = resolve(feature.params.get("radius", 1), params)
        half = np.array([radius, radius, radius], dtype=float)
    else:
        ring = resolve(feature.params.get("radius", 1), params)
        tube = resolve(feature.params.get("tube", 0.25), params)
        half = np.array([ring + tube, ring + tube, tube], dtype=float)

    rotation = feature.params.get("rotate")
    if rotation is not None:
        half = _rotated_half_extent(half, resolve_vec(rotation, params))
    return centre - half, centre + half


def _rotated_half_extent(half: np.ndarray, degrees: np.ndarray) -> np.ndarray:
    """Half extent of the box that contains a rotated box.

    Every corner is carried through the same rotation the field uses, and the
    box around those eight points is the answer. This is exact for a box and
    a safe over-estimate for the round shapes, which is the right way round
    for something that only sizes a lattice.
    """
    signs = np.array(
        [[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=float
    )
    # rotate_points carries a world point into the feature's frame, so the
    # matrix that carries the shape back out is its transpose. Reading that
    # matrix off the basis vectors keeps this in step with the field itself,
    # whatever convention the field settles on.
    to_local = rotate_points(np.eye(3), degrees).T
    corners = (signs * half) @ to_local
    return np.abs(corners).max(axis=0)


def feature_sdf(feature: Feature, points: np.ndarray, params: dict[str, float]) -> np.ndarray:
    """Distance from each point to the feature's surface, negative inside."""
    local = points - resolve_vec(feature.params.get("center"), params)
    rotation = feature.params.get("rotate")
    if rotation is not None:
        local = rotate_points(local, resolve_vec(rotation, params))

    if feature.type == "box":
        half = resolve_vec(feature.params.get("size"), params, (1, 1, 1)) / 2.0
        radius = float(resolve(feature.params.get("round", 0), params))
        corner = np.abs(local) - (half - radius)
        outside = np.linalg.norm(np.maximum(corner, 0.0), axis=-1)
        inside = np.minimum(np.max(corner, axis=-1), 0.0)
        return outside + inside - radius

    if feature.type == "sphere":
        return np.linalg.norm(local, axis=-1) - resolve(feature.params.get("radius", 1), params)

    if feature.type == "cylinder":
        axis = "xyz".index(str(feature.params.get("axis", "z")).lower())
        others = [i for i in range(3) if i != axis]
        radius = resolve(feature.params.get("radius", 1), params)
        half_height = resolve(feature.params.get("height", 1), params) / 2.0
        radial = np.linalg.norm(local[..., others], axis=-1) - radius
        axial = np.abs(local[..., axis]) - half_height
        outside = np.linalg.norm(
            np.stack([np.maximum(radial, 0.0), np.maximum(axial, 0.0)], axis=-1), axis=-1
        )
        return outside + np.minimum(np.maximum(radial, axial), 0.0)

    if feature.type == "torus":
        ring = resolve(feature.params.get("radius", 1), params)
        tube = resolve(feature.params.get("tube", 0.25), params)
        planar = np.linalg.norm(local[..., [0, 1]], axis=-1) - ring
        return np.linalg.norm(np.stack([planar, local[..., 2]], axis=-1), axis=-1) - tube

    raise ValueError(f"unhandled feature type {feature.type!r}")


def rotate_points(points: np.ndarray, degrees: np.ndarray) -> np.ndarray:
    """Move points into the feature's own frame, rotating about X then Y then Z."""
    rx, ry, rz = np.radians(degrees)
    for axis, angle in ((0, rx), (1, ry), (2, rz)):
        if abs(angle) < 1e-12:
            continue
        cos_a, sin_a = math.cos(-angle), math.sin(-angle)
        first, second = [k for k in range(3) if k != axis]
        a, b = points[..., first].copy(), points[..., second].copy()
        points = points.copy()
        points[..., first] = a * cos_a - b * sin_a
        points[..., second] = a * sin_a + b * cos_a
    return points


def smooth_union(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """Union of two fields. A positive k rounds the join by that radius."""
    if k <= 0:
        return np.minimum(a, b)
    blend = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - blend) + a * blend - k * blend * (1.0 - blend)


def smooth_subtract(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """Remove b from a, rounding the resulting edge by k."""
    if k <= 0:
        return np.maximum(a, -b)
    blend = np.clip(0.5 - 0.5 * (b + a) / k, 0.0, 1.0)
    return a * (1 - blend) + (-b) * blend + k * blend * (1.0 - blend)


def smooth_intersect(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """Keep only what is inside both fields, rounding the edge by k."""
    if k <= 0:
        return np.maximum(a, b)
    blend = np.clip(0.5 - 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - blend) + a * blend + k * blend * (1.0 - blend)
