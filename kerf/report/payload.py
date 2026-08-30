"""Building the geometry payload the report viewer draws.

Surfaces are sorted into three groups so the viewer can colour them: surface
both revisions share, surface only the new one has, and surface only the old
one has.
"""

from __future__ import annotations

import base64
from typing import Optional

import numpy as np

from ..geometry import Mesh, common_grid, voxelize

MAX_VIEWER_TRIANGLES = 260_000


def encode(array: np.ndarray) -> str:
    """Pack a numpy array into base64 so it can sit inside the HTML."""
    return base64.b64encode(np.ascontiguousarray(array).tobytes()).decode()


def triangles_outside(mesh: Mesh, grid: np.ndarray, origin: np.ndarray, pitch: float) -> np.ndarray:
    """True where a triangle belongs to surface the other solid does not have.

    Sampling the bare centroid is not enough: a triangle on a face the two
    revisions share sits exactly on the other solid's boundary, where the
    voxel answer is a coin flip.  Stepping a little way along the inward
    normal moves the sample decisively inside for shared surfaces while
    leaving genuinely new surface outside.
    """
    if mesh.empty():
        return np.zeros(0, dtype=bool)
    tris = mesh.triangles()
    centres = tris.mean(axis=1)
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.where(lengths == 0, 1.0, lengths)
    probes = centres - normals * (pitch * 0.9)
    idx = np.floor((probes - origin) / pitch).astype(int)
    ok = np.all((idx >= 0) & (idx < np.asarray(grid.shape)), axis=1)
    inside = np.zeros(len(tris), dtype=bool)
    if ok.any():
        sel = idx[ok]
        inside[ok] = grid[sel[:, 0], sel[:, 1], sel[:, 2]]
    return ~inside


def viewer_payload(old: Optional[Mesh], new: Optional[Mesh],
                   resolution: int = 56) -> Optional[dict]:
    meshes = [m for m in (old, new) if m is not None and not m.empty()]
    if not meshes:
        return None
    total = sum(len(m.faces) for m in meshes)
    if total > MAX_VIEWER_TRIANGLES:
        return None

    lo = np.min([m.bbox()[0] for m in meshes], axis=0)
    hi = np.max([m.bbox()[1] for m in meshes], axis=0)
    centre = (lo + hi) / 2.0
    radius = float(max(np.linalg.norm(hi - lo) / 2.0, 1e-6))

    payload: dict = {
        "center": centre.tolist(), "radius": radius,
        "min": lo.tolist(), "max": hi.tolist(), "groups": {},
    }

    if new is not None and not new.empty():
        payload["newPos"] = encode(new.vertices.astype(np.float32))
        payload["groups"]["newAll"] = {
            "idx": encode(new.faces.astype(np.uint32)), "count": int(new.faces.size), "src": "new"
        }
    if old is not None and not old.empty():
        payload["oldPos"] = encode(old.vertices.astype(np.float32))
        payload["groups"]["oldAll"] = {
            "idx": encode(old.faces.astype(np.uint32)), "count": int(old.faces.size), "src": "old"
        }

    if old is not None and new is not None and not old.empty() and not new.empty():
        origin, pitch, dims = common_grid([old, new], resolution)
        grid_old = voxelize(old, origin, pitch, dims)
        grid_new = voxelize(new, origin, pitch, dims)
        added = triangles_outside(new, grid_old, origin, pitch)
        removed = triangles_outside(old, grid_new, origin, pitch)
        kept_faces = new.faces[~added]
        add_faces = new.faces[added]
        rem_faces = old.faces[removed]
        payload["groups"]["kept"] = {
            "idx": encode(kept_faces.astype(np.uint32)), "count": int(kept_faces.size), "src": "new"
        }
        payload["groups"]["added"] = {
            "idx": encode(add_faces.astype(np.uint32)), "count": int(add_faces.size), "src": "new"
        }
        payload["groups"]["removed"] = {
            "idx": encode(rem_faces.astype(np.uint32)), "count": int(rem_faces.size), "src": "old"
        }
    return payload
