"""A triangle mesh and the measurements kerf reports about it."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Mesh:
    vertices: np.ndarray   # shape (N, 3), float64
    faces: np.ndarray      # shape (M, 3), int32 indices into vertices

    @staticmethod
    def from_triangles(triangles: np.ndarray, weld_tol: float = 1e-9) -> "Mesh":
        """Build an indexed mesh from a raw triangle soup of shape (M, 3, 3).

        Vertices closer together than weld_tol collapse into one, which is how
        an STL turns back into a connected surface.
        """
        triangles = np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)
        if len(triangles) == 0:
            return Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32))
        corners = triangles.reshape(-1, 3)
        quantized = np.round(corners / max(weld_tol, 1e-12)).astype(np.int64)
        _, first, inverse = np.unique(
            quantized, axis=0, return_index=True, return_inverse=True
        )
        vertices = corners[first]
        faces = inverse.reshape(-1, 3).astype(np.int32)
        keep = (
            (faces[:, 0] != faces[:, 1])
            & (faces[:, 1] != faces[:, 2])
            & (faces[:, 0] != faces[:, 2])
        )
        return Mesh(vertices, faces[keep])

    def empty(self) -> bool:
        return len(self.faces) == 0

    def triangles(self) -> np.ndarray:
        """Corner coordinates of every face, shape (M, 3, 3)."""
        if self.empty():
            return np.zeros((0, 3, 3))
        return self.vertices[self.faces]

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        if self.empty():
            zero = np.zeros(3)
            return zero, zero
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def area(self) -> float:
        faces = self.triangles()
        if len(faces) == 0:
            return 0.0
        cross = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
        return float(0.5 * np.linalg.norm(cross, axis=1).sum())

    def volume(self) -> float:
        """Enclosed volume, from the divergence theorem over the faces."""
        faces = self.triangles()
        if len(faces) == 0:
            return 0.0
        a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
        return float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0))

    def centroid(self) -> np.ndarray:
        """Centre of volume. An open shell has no volume centroid, so this
        falls back to the area centroid and then to the vertex mean."""
        faces = self.triangles()
        if len(faces) == 0:
            return np.zeros(3)
        a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
        volumes = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
        total = volumes.sum()
        if abs(total) < 1e-12:
            areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
            if areas.sum() < 1e-12:
                return self.vertices.mean(axis=0)
            return (faces.mean(axis=1) * areas[:, None]).sum(axis=0) / areas.sum()
        return ((a + b + c) / 4.0 * volumes[:, None]).sum(axis=0) / total

    def is_watertight(self) -> bool:
        """True when every directed edge appears once and its reverse also
        appears once.

        The directed form catches inconsistent winding as well as holes. A
        mesh with inconsistent winding cannot be sliced, so it is worth
        knowing about before the file reaches a printer.
        """
        if self.empty():
            return False
        faces = self.faces.astype(np.int64)
        count = len(self.vertices)
        directed = np.concatenate([
            faces[:, 0] * count + faces[:, 1],
            faces[:, 1] * count + faces[:, 2],
            faces[:, 2] * count + faces[:, 0],
        ])
        reversed_edges = np.concatenate([
            faces[:, 1] * count + faces[:, 0],
            faces[:, 2] * count + faces[:, 1],
            faces[:, 0] * count + faces[:, 2],
        ])
        if len(np.unique(directed)) != len(directed):
            return False
        return bool(np.isin(reversed_edges, directed).all())

    def outward_fraction(self) -> float:
        """Share of faces whose normal points away from the centroid. A convex
        solid scores 1.0, and a solid with internal holes scores lower because
        the faces inside a bore correctly point inward."""
        faces = self.triangles()
        if len(faces) == 0:
            return 0.0
        normals = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
        offsets = faces.mean(axis=1) - self.centroid()
        return float((np.einsum("ij,ij->i", normals, offsets) > 0).mean())

    def component_count(self) -> int:
        """Number of separate bodies, found by union of shared vertices."""
        if self.empty():
            return 0
        parent = np.arange(len(self.vertices))

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for face in self.faces:
            root = find(int(face[0]))
            for other in face[1:]:
                other_root = find(int(other))
                if root != other_root:
                    parent[other_root] = root
        used = np.unique(self.faces)
        return len({find(int(vertex)) for vertex in used})

    def stats(self) -> dict:
        low, high = self.bbox()
        return {
            "triangles": int(len(self.faces)),
            "vertices": int(len(self.vertices)),
            "volume": self.volume(),
            "area": self.area(),
            "bbox_min": low.tolist(),
            "bbox_max": high.tolist(),
            "size": (high - low).tolist(),
            "centroid": self.centroid().tolist(),
            "watertight": self.is_watertight(),
            "components": self.component_count(),
        }
