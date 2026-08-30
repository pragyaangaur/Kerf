"""Reading and writing Wavefront OBJ.

Only geometry is handled. Materials and texture coordinates are skipped, and
a polygon with more than three corners is split into a fan of triangles.
"""

from __future__ import annotations

import numpy as np

from ..geometry import Mesh


def load(data: bytes) -> Mesh:
    verts: list[list[float]] = []
    faces: list[tuple[int, int, int]] = []
    for line in data.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif parts[0] == "f" and len(parts) >= 4:
            idx = []
            for tok in parts[1:]:
                raw = int(tok.split("/")[0])
                idx.append(raw - 1 if raw > 0 else len(verts) + raw)
            for i in range(1, len(idx) - 1):     # split the polygon into a fan
                faces.append((idx[0], idx[i], idx[i + 1]))
    v = np.asarray(verts, dtype=np.float64) if verts else np.zeros((0, 3))
    f = np.asarray(faces, dtype=np.int32) if faces else np.zeros((0, 3), dtype=np.int32)
    return Mesh(v, f)


def dump(mesh: Mesh, name: str = "kerf") -> bytes:
    lines = [f"# kerf export: {name}"]
    lines += ["v %.6f %.6f %.6f" % tuple(v) for v in mesh.vertices]
    lines += ["f %d %d %d" % (a + 1, b + 1, c + 1) for a, b, c in mesh.faces]
    return ("\n".join(lines) + "\n").encode()
