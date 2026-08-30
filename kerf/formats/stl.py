"""Reading and writing STL, in both the binary and the text form."""

from __future__ import annotations

import struct

import numpy as np

from ..geometry import Mesh


def looks_binary(data: bytes) -> bool:
    if len(data) < 84:
        return False
    if data[:5].lstrip().lower().startswith(b"solid"):
        # A text style header proves nothing, because plenty of binary files
        # start with the word solid. The file length is the reliable test: a
        # binary STL is exactly 84 bytes plus 50 bytes per triangle.
        (count,) = struct.unpack("<I", data[80:84])
        return len(data) == 84 + count * 50
    return True


def load(data: bytes) -> Mesh:
    if looks_binary(data):
        return _load_binary(data)
    return _load_ascii(data)


def _load_binary(data: bytes) -> Mesh:
    (count,) = struct.unpack("<I", data[80:84])
    expected = 84 + count * 50
    if len(data) < expected:
        raise ValueError(f"truncated binary STL: want {expected} bytes, have {len(data)}")
    rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    arr = np.frombuffer(data[84:expected], dtype=rec, count=count)
    return Mesh.from_triangles(arr["v"].astype(np.float64))


def _load_ascii(data: bytes) -> Mesh:
    verts: list[list[float]] = []
    for line in data.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if parts and parts[0] == "vertex" and len(parts) >= 4:
            verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
    if len(verts) % 3:
        verts = verts[: len(verts) - len(verts) % 3]
    return Mesh.from_triangles(np.asarray(verts, dtype=np.float64).reshape(-1, 3, 3))


def dump_binary(mesh: Mesh, header: bytes = b"kerf") -> bytes:
    tris = mesh.triangles().astype(np.float32)
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, np.where(lengths == 0, 1, lengths))
    out = bytearray(header[:80].ljust(80, b"\0"))
    out += struct.pack("<I", len(tris))
    for n, t in zip(normals.astype(np.float32), tris):
        out += struct.pack("<12fH", *n, *t[0], *t[1], *t[2], 0)
    return bytes(out)


def dump_ascii(mesh: Mesh, name: str = "kerf") -> bytes:
    tris = mesh.triangles()
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, np.where(lengths == 0, 1, lengths))
    lines = [f"solid {name}"]
    for n, t in zip(normals, tris):
        lines.append("  facet normal %.6e %.6e %.6e" % tuple(n))
        lines.append("    outer loop")
        for v in t:
            lines.append("      vertex %.6e %.6e %.6e" % tuple(v))
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append(f"endsolid {name}")
    return ("\n".join(lines) + "\n").encode()
