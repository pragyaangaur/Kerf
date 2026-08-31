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
            try:
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            except ValueError:
                continue
        elif parts[0] == "f" and len(parts) >= 4:
            idx = []
            for tok in parts[1:]:
                try:
                    raw = int(tok.split("/")[0])
                except ValueError:
                    idx = []
                    break
                if raw == 0:
                    idx = []
                    break
                # A negative index counts back from the vertices seen so far,
                # which is why this is resolved as the file is read.
                idx.append(raw - 1 if raw > 0 else len(verts) + raw)
            # A face that points past the vertex list is a corrupt file, and
            # keeping it turns every later measurement into an IndexError far
            # away from the line that caused it.
            if not idx or any(i < 0 or i >= len(verts) for i in idx):
                continue
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
