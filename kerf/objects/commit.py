"""A commit points at one tree and at the revisions it came from."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Commit:
    tree: str
    parents: list[str]
    author: str
    timestamp: int
    message: str
    meta: dict[str, str] = field(default_factory=dict)

    def serialize(self) -> bytes:
        lines = [f"tree {self.tree}"]
        lines += [f"parent {parent}" for parent in self.parents]
        lines.append(f"author {self.author}")
        lines.append(f"timestamp {self.timestamp}")
        for key in sorted(self.meta):
            lines.append(f"meta {key} {self.meta[key]}")
        lines.append("")
        lines.append(self.message)
        return "\n".join(lines).encode()

    @staticmethod
    def deserialize(payload: bytes) -> "Commit":
        header, _, message = payload.decode().partition("\n\n")
        tree, parents, author, timestamp, meta = "", [], "", 0, {}
        for line in header.splitlines():
            key, _, value = line.partition(" ")
            if key == "tree":
                tree = value
            elif key == "parent":
                parents.append(value)
            elif key == "author":
                author = value
            elif key == "timestamp":
                timestamp = int(value)
            elif key == "meta":
                meta_key, _, meta_value = value.partition(" ")
                meta[meta_key] = meta_value
        return Commit(tree, parents, author, timestamp, message, meta)

    def short(self) -> str:
        """The first line of the message, which is what logs show."""
        return self.message.splitlines()[0] if self.message else ""
