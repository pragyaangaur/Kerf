"""Deciding whether two meshes describe the same solid.

Two questions get asked, in order. The first is whether the shapes are
exactly the same once the file format's freedom is removed, and that is what
geometry_hash answers. The second is whether the shapes agree to within a
tolerance, and that is what equivalent answers. The second question exists
because some exporters write float noise into a part nobody edited.
"""

from __future__ import annotations

import hashlib

import numpy as np

from .mesh import Mesh


def geometry_hash(mesh: Mesh, rel_tol: float = 1e-6) -> str:
    """Hash the shape rather than the file.

    Triangle order, the order of corners inside a triangle, vertex numbering
    and float noise below the tolerance all wash out. Winding is preserved,
    so a solid and its inside out twin hash differently.
    """
    if mesh.empty():
        return hashlib.sha256(b"kerf-empty-mesh").hexdigest()

    low, high = mesh.bbox()
    diagonal = float(np.linalg.norm(high - low))
    tolerance = max(diagonal * rel_tol, 1e-9)

    triangles = mesh.triangles()
    quantized = np.round(triangles / tolerance).astype(np.int64)

    # Rotate each triangle so its smallest corner comes first. Rotation keeps
    # the winding, so the surface orientation survives the canonical form.
    flat = quantized.reshape(len(quantized), 3, 3)
    leading = np.lexsort((flat[:, :, 2], flat[:, :, 1], flat[:, :, 0]), axis=1)[:, 0]
    order = (np.arange(3)[None, :] + leading[:, None]) % 3
    rotated = np.take_along_axis(quantized, order[:, :, None], axis=1)

    rows = rotated.reshape(len(quantized), 9)
    sort_order = np.lexsort(tuple(rows[:, i] for i in range(8, -1, -1)))
    rows = rows[sort_order]

    digest = hashlib.sha256()
    digest.update(f"kerf-geom-v1 {tolerance:.12e} {len(rows)}\n".encode())
    digest.update(np.ascontiguousarray(rows, dtype=np.int64).tobytes())
    return digest.hexdigest()


def max_vertex_deviation(a: Mesh, b: Mesh, cell: float | None = None) -> float:
    """Largest distance from a vertex of b to the nearest vertex of a.

    Vertices are paired with a spatial hash rather than by index or by sort
    order. CAD meshes contain many exactly coincident coordinates, and any
    ordering key reshuffles them under the float noise this function exists to
    see through. A wrong pairing can only happen between points that are
    already almost in the same place, so the answer stays an upper bound.

    Returns infinity when the meshes cannot correspond at all.
    """
    if a.empty() or b.empty():
        return float("inf")
    if len(a.vertices) != len(b.vertices) or len(a.faces) != len(b.faces):
        return float("inf")

    low, high = a.bbox()
    diagonal = float(np.linalg.norm(high - low)) or 1.0
    cell = cell or diagonal * 1e-4

    origin = np.minimum(low, b.bbox()[0]) - cell
    points_a = a.vertices - origin
    points_b = b.vertices - origin

    index_a = np.floor(points_a / cell).astype(np.int64)
    index_b = np.floor(points_b / cell).astype(np.int64)
    stride = np.maximum(index_a.max(axis=0), index_b.max(axis=0)) + 3

    def code(index: np.ndarray) -> np.ndarray:
        return (index[:, 0] * stride[1] + index[:, 1]) * stride[2] + index[:, 2]

    codes = code(index_a)
    order = np.argsort(codes, kind="stable")
    sorted_codes = codes[order]

    best = np.full(len(points_b), np.inf)
    neighbourhood = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)]
    for offset in neighbourhood:
        probe = code(index_b + np.asarray(offset, dtype=np.int64))
        start = np.searchsorted(sorted_codes, probe, side="left")
        stop = np.searchsorted(sorted_codes, probe, side="right")
        depth = int((stop - start).max()) if len(start) else 0
        for step in range(depth):
            usable = start + step < stop
            if not usable.any():
                break
            rows = np.nonzero(usable)[0]
            candidates = order[start[rows] + step]
            distance = np.linalg.norm(points_a[candidates] - points_b[rows], axis=1)
            np.minimum.at(best, rows, distance)
    return float(best.max())


def equivalent(a: Mesh, b: Mesh, rel_tol: float = 1e-5) -> tuple[bool, float]:
    """Are these the same solid to within a fraction of its own size?

    This recognises the same tessellation with moved coordinates, which is
    what a re-export produces. A genuine re-mesh needs a surface distance
    measure to judge fairly, so this function reports it as a difference and
    kerf says so rather than guessing.
    """
    if a.empty() and b.empty():
        return True, 0.0
    low, high = a.bbox()
    diagonal = float(np.linalg.norm(high - low)) or 1.0
    deviation = max_vertex_deviation(a, b)
    return deviation <= diagonal * rel_tol, deviation
