"""A tree is the list of files in one revision.

Each entry carries two identifiers. The object id is the hash of the exact
bytes, and the geometry id is the hash of the shape those bytes describe. A
part exported twice from the same model gets two object ids and one geometry
id, and everything a user sees is driven by the geometry id.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TreeEntry:
    path: str          # repository relative path, always with forward slashes
    oid: str           # hash of the file bytes
    gid: str           # hash of the geometry, empty for files kerf cannot read
    kind: str          # one of mesh, parametric, opaque, file
    size: int = 0

    def line(self) -> str:
        return "\t".join([self.kind, self.oid, self.gid, str(self.size), self.path])

    @staticmethod
    def parse(line: str) -> "TreeEntry":
        kind, oid, gid, size, path = line.split("\t", 4)
        return TreeEntry(path=path, oid=oid, gid=gid, kind=kind, size=int(size))


@dataclass
class Tree:
    entries: dict[str, TreeEntry] = field(default_factory=dict)

    def serialize(self) -> bytes:
        rows = [self.entries[path].line() for path in sorted(self.entries)]
        return ("\n".join(rows) + ("\n" if rows else "")).encode()

    @staticmethod
    def deserialize(payload: bytes) -> "Tree":
        tree = Tree()
        for line in payload.decode().splitlines():
            if line.strip():
                entry = TreeEntry.parse(line)
                tree.entries[entry.path] = entry
        return tree

    def paths(self) -> list[str]:
        return sorted(self.entries)
