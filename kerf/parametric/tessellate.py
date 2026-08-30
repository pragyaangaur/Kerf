"""Turning a distance field into triangles with surface nets.

One vertex is placed in every cell where the field changes sign, at the mean
of the crossings on that cell's edges. Quads are then stitched between the
four cells that share a crossing edge. The result is watertight and wound
consistently, which the test suite checks, because a mesh with mixed winding
cannot be sliced.
"""

from __future__ import annotations

import numpy as np

from ..geometry.mesh import Mesh

# Corner index inside a cell is 4*dx + 2*dy + dz.
CORNERS = np.array([[dx, dy, dz] for dx in (0, 1) for dy in (0, 1) for dz in (0, 1)])

EDGES = [
    (0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
    (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7),
]


def surface_nets(values: np.ndarray, origin: np.ndarray, pitch: float) -> Mesh:
    """Build a mesh for the zero level of a sampled field."""
    nx, ny, nz = (size - 1 for size in values.shape)
    if min(nx, ny, nz) < 1:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32))

    inside = values < 0.0
    corner_values = np.empty((nx, ny, nz, 8))
    corner_inside = np.empty((nx, ny, nz, 8), dtype=bool)
    for index, (dx, dy, dz) in enumerate(CORNERS):
        corner_values[..., index] = values[dx:dx + nx, dy:dy + ny, dz:dz + nz]
        corner_inside[..., index] = inside[dx:dx + nx, dy:dy + ny, dz:dz + nz]

    active = corner_inside.any(axis=-1) & (~corner_inside).any(axis=-1)
    if not active.any():
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32))

    accumulated = np.zeros((nx, ny, nz, 3))
    crossings = np.zeros((nx, ny, nz))
    for first, second in EDGES:
        value_a, value_b = corner_values[..., first], corner_values[..., second]
        crosses = corner_inside[..., first] != corner_inside[..., second]
        denominator = np.where(np.abs(value_a - value_b) < 1e-30, 1e-30, value_a - value_b)
        along = np.clip(value_a / denominator, 0.0, 1.0)
        corner_a = CORNERS[first].astype(float)
        corner_b = CORNERS[second].astype(float)
        point = corner_a[None, None, None, :] + along[..., None] * (corner_b - corner_a)[None, None, None, :]
        accumulated += np.where(crosses[..., None], point, 0.0)
        crossings += crosses

    divisor = np.where(crossings == 0, 1.0, crossings)
    local = accumulated / divisor[..., None]
    cells = np.argwhere(active)
    vertices = origin + (cells + local[tuple(cells.T)]) * pitch

    vertex_of_cell = -np.ones((nx, ny, nz), dtype=np.int64)
    vertex_of_cell[tuple(cells.T)] = np.arange(len(cells))

    faces: list[np.ndarray] = []
    for axis in range(3):
        u, v = [k for k in range(3) if k != axis]
        low = [slice(None)] * 3
        high = [slice(None)] * 3
        low[axis] = slice(0, values.shape[axis] - 1)
        high[axis] = slice(1, values.shape[axis])
        # Trim the two perpendicular directions so all four neighbouring cells exist.
        for window in (low, high):
            window[u] = slice(1, values.shape[u] - 1)
            window[v] = slice(1, values.shape[v] - 1)
        inside_low = inside[tuple(low)]
        inside_high = inside[tuple(high)]
        crosses = inside_low != inside_high
        if not crosses.any():
            continue
        positions = np.argwhere(crosses)
        base = np.zeros((len(positions), 3), dtype=np.int64)
        base[:, axis] = positions[:, axis]
        base[:, u] = positions[:, u] + 1
        base[:, v] = positions[:, v] + 1

        def neighbour(du: int, dv: int) -> np.ndarray:
            cell = base.copy()
            cell[:, u] -= du
            cell[:, v] -= dv
            return vertex_of_cell[cell[:, 0], cell[:, 1], cell[:, 2]]

        q00, q10, q11, q01 = neighbour(1, 1), neighbour(0, 1), neighbour(0, 0), neighbour(1, 0)
        usable = (q00 >= 0) & (q10 >= 0) & (q11 >= 0) & (q01 >= 0)
        if not usable.any():
            continue
        q00, q10, q11, q01 = q00[usable], q10[usable], q11[usable], q01[usable]
        flip = inside_low[tuple(positions[usable].T)]
        if axis == 1:
            # The handedness of the two in plane directions reverses for y.
            flip = ~flip
        # The field is negative inside, so the outward face points away from
        # the solid. Reverse once more to get outward normals.
        flip = ~flip
        first_half = np.stack([q00, q10, q11], axis=1)
        second_half = np.stack([q00, q11, q01], axis=1)
        faces.append(np.where(flip[:, None], first_half[:, ::-1], first_half))
        faces.append(np.where(flip[:, None], second_half[:, ::-1], second_half))

    if not faces:
        return Mesh(vertices, np.zeros((0, 3), dtype=np.int32))
    stacked = np.vstack(faces).astype(np.int32)
    keep = (
        (stacked[:, 0] != stacked[:, 1])
        & (stacked[:, 1] != stacked[:, 2])
        & (stacked[:, 0] != stacked[:, 2])
    )
    return Mesh(vertices, stacked[keep])
