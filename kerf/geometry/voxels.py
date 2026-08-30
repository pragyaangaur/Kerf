"""Turning surfaces into occupancy grids, so two revisions can be subtracted.

A mesh diff needs an answer to "where did material appear or disappear", and
the surfaces themselves cannot answer it. Both revisions are sampled onto one
shared lattice instead, and the difference between the two occupancy grids is
the answer.
"""

from __future__ import annotations

import numpy as np

from .mesh import Mesh


def voxelize(
    mesh: Mesh, origin: np.ndarray, pitch: float, dims: tuple[int, int, int]
) -> np.ndarray:
    """Fill a boolean grid with the cells whose centres lie inside the mesh.

    Each column of cells is tested by counting how many faces a ray along +Z
    crosses above it. An odd count means the cell is inside. This assumes a
    closed surface, and an open shell degrades to a partial fill rather than
    an error.
    """
    nx, ny, nz = dims
    grid = np.zeros((nx, ny, nz), dtype=bool)
    if mesh.empty():
        return grid

    triangles = mesh.triangles()
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]

    xs = origin[0] + (np.arange(nx) + 0.5) * pitch
    ys = origin[1] + (np.arange(ny) + 0.5) * pitch
    zs = origin[2] + (np.arange(nz) + 0.5) * pitch

    column_ids: list[np.ndarray] = []
    column_zs: list[np.ndarray] = []

    footprint = triangles[:, :, :2]
    low = footprint.min(axis=1)
    high = footprint.max(axis=1)

    i0 = np.clip(np.ceil((low[:, 0] - origin[0]) / pitch - 0.5).astype(int), 0, nx)
    i1 = np.clip(np.floor((high[:, 0] - origin[0]) / pitch - 0.5).astype(int) + 1, 0, nx)
    j0 = np.clip(np.ceil((low[:, 1] - origin[1]) / pitch - 0.5).astype(int), 0, ny)
    j1 = np.clip(np.floor((high[:, 1] - origin[1]) / pitch - 0.5).astype(int) + 1, 0, ny)

    for face in range(len(triangles)):
        if i1[face] <= i0[face] or j1[face] <= j0[face]:
            continue
        ax, ay = a[face, 0], a[face, 1]
        e0x, e0y = b[face, 0] - ax, b[face, 1] - ay
        e1x, e1y = c[face, 0] - ax, c[face, 1] - ay
        determinant = e0x * e1y - e1x * e0y
        if abs(determinant) < 1e-14:
            # The face is edge on to the ray direction and cannot be crossed.
            continue
        gx = xs[i0[face]:i1[face]]
        gy = ys[j0[face]:j1[face]]
        px = gx[:, None] - ax
        py = gy[None, :] - ay
        u = (px * e1y - py * e1x) / determinant
        v = (py * e0x - px * e0y) / determinant
        inside = (u >= 0) & (v >= 0) & (u + v <= 1)
        if not inside.any():
            continue
        z_hit = a[face, 2] + u * (b[face, 2] - a[face, 2]) + v * (c[face, 2] - a[face, 2])
        ii, jj = np.nonzero(inside)
        column_ids.append((ii + i0[face]) * ny + (jj + j0[face]))
        column_zs.append(z_hit[ii, jj])

    if not column_ids:
        return grid

    columns = np.concatenate(column_ids)
    hits = np.concatenate(column_zs)

    order = np.lexsort((hits, columns))
    columns, hits = columns[order], hits[order]

    flat = grid.reshape(nx * ny, nz)
    bounds = np.searchsorted(columns, np.arange(nx * ny + 1))
    for column in np.unique(columns):
        segment = hits[bounds[column]:bounds[column + 1]]
        if len(segment) < 2:
            continue
        above = len(segment) - np.searchsorted(segment, zs, side="left")
        flat[column] = (above % 2) == 1
    return grid


def common_grid(meshes: list[Mesh], resolution: int = 64, pad: float = 0.06):
    """Choose one lattice that covers every mesh, with a little room around it."""
    boxes = [mesh.bbox() for mesh in meshes if not mesh.empty()]
    if not boxes:
        return np.zeros(3), 1.0, (1, 1, 1)
    low = np.min([box[0] for box in boxes], axis=0)
    high = np.max([box[1] for box in boxes], axis=0)
    longest = float((high - low).max()) or 1.0
    margin = longest * pad
    low = low - margin
    high = high + margin
    pitch = float((high - low).max()) / resolution
    dims = tuple(int(max(1, np.ceil(span / pitch))) for span in (high - low))
    return low, pitch, dims


def interior_seeds(grid: np.ndarray) -> np.ndarray:
    """Cells that have all six neighbours occupied.

    A changed layer only one cell thick is thinner than the measurement
    itself, and that is what surface noise and re-tessellation look like. A
    region holding at least one seed cell is thicker than the lattice, so it
    is a real change.
    """
    if grid.ndim != 3 or min(grid.shape) < 3:
        return np.zeros_like(grid)
    result = grid.copy()
    for axis in range(3):
        lower = np.roll(grid, 1, axis=axis)
        upper = np.roll(grid, -1, axis=axis)
        edge_low = [slice(None)] * 3
        edge_high = [slice(None)] * 3
        edge_low[axis] = 0
        edge_high[axis] = -1
        lower[tuple(edge_low)] = False
        upper[tuple(edge_high)] = False
        result &= lower & upper
    return result


def label_regions(grid: np.ndarray) -> tuple[np.ndarray, int]:
    """Group occupied cells into connected regions, joined across faces."""
    occupied = np.argwhere(grid)
    labels = np.zeros(grid.shape, dtype=np.int32)
    if len(occupied) == 0:
        return labels, 0

    lookup = -np.ones(grid.shape, dtype=np.int32)
    lookup[tuple(occupied.T)] = np.arange(len(occupied))
    parent = np.arange(len(occupied))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for axis in range(3):
        lower = [slice(None)] * 3
        upper = [slice(None)] * 3
        lower[axis] = slice(0, -1)
        upper[axis] = slice(1, None)
        both = grid[tuple(lower)] & grid[tuple(upper)]
        if not both.any():
            continue
        pairs = np.argwhere(both)
        left = lookup[tuple(pairs.T)]
        shifted = pairs.copy()
        shifted[:, axis] += 1
        right = lookup[tuple(shifted.T)]
        for a, b in zip(left, right):
            union(int(a), int(b))

    roots = np.array([find(i) for i in range(len(occupied))])
    unique, compact = np.unique(roots, return_inverse=True)
    labels[tuple(occupied.T)] = compact + 1
    return labels, len(unique)
