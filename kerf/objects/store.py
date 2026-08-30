"""Content addressed storage for every object kerf keeps.

An object is identified by the SHA-256 of its serialized form, using the same
framing git uses: the type name, a space, the payload length, a null byte,
then the payload. Two identical parts therefore cost one copy on disk no
matter how many revisions reference them.
"""

from __future__ import annotations

import hashlib
import os
import zlib
from typing import Iterator, Optional


def hash_object(kind: str, payload: bytes) -> str:
    """Return the object id for a payload of the given type."""
    digest = hashlib.sha256()
    digest.update(f"{kind} {len(payload)}\0".encode())
    digest.update(payload)
    return digest.hexdigest()


class ObjectStore:
    """Loose objects on disk, one file per object, sharded by the first byte."""

    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _path(self, oid: str) -> str:
        return os.path.join(self.root, oid[:2], oid[2:])

    def exists(self, oid: str) -> bool:
        return os.path.exists(self._path(oid))

    def put(self, kind: str, payload: bytes) -> str:
        """Store a payload and return its object id. Writing the same payload
        twice is free, because the second write finds the file already there."""
        oid = hash_object(kind, payload)
        path = self._path(oid)
        if os.path.exists(path):
            return oid
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = f"{kind} {len(payload)}\0".encode() + payload
        temp = path + ".tmp"
        with open(temp, "wb") as handle:
            handle.write(zlib.compress(body, 6))
        os.replace(temp, path)
        return oid

    def get(self, oid: str) -> tuple[str, bytes]:
        """Return the type and payload of a stored object."""
        path = self._path(oid)
        if not os.path.exists(path):
            raise KeyError(f"object not found: {oid[:12]}")
        raw = zlib.decompress(open(path, "rb").read())
        header, _, payload = raw.partition(b"\0")
        kind, _, _ = header.decode().partition(" ")
        return kind, payload

    def get_typed(self, oid: str, expect: str) -> bytes:
        """Return the payload of an object, and fail if it is the wrong type."""
        kind, payload = self.get(oid)
        if kind != expect:
            raise TypeError(f"{oid[:12]} is a {kind}, expected {expect}")
        return payload

    def resolve_prefix(self, prefix: str) -> Optional[str]:
        """Expand a shortened object id. Returns None if the prefix is
        ambiguous or matches nothing."""
        if len(prefix) < 4:
            return None
        shard = os.path.join(self.root, prefix[:2])
        if not os.path.isdir(shard):
            return None
        rest = prefix[2:]
        matches = [
            name for name in os.listdir(shard)
            if name.startswith(rest) and not name.endswith(".tmp")
        ]
        return prefix[:2] + matches[0] if len(matches) == 1 else None

    def iter_oids(self) -> Iterator[str]:
        for shard in sorted(os.listdir(self.root)):
            path = os.path.join(self.root, shard)
            if not os.path.isdir(path):
                continue
            for name in sorted(os.listdir(path)):
                if not name.endswith(".tmp"):
                    yield shard + name

    def total_bytes(self) -> int:
        total = 0
        for shard in os.listdir(self.root):
            path = os.path.join(self.root, shard)
            if os.path.isdir(path):
                for name in os.listdir(path):
                    total += os.path.getsize(os.path.join(path, name))
        return total
