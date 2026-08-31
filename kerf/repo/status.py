"""What changed, described in geometric terms.

Status separates a real edit from a file that was written again with no
design change. That distinction is the whole reason kerf exists, so it
belongs in the first command anybody runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .. import model as model_mod
from ..objects import hash_object


@dataclass
class StatusEntry:
    path: str
    state: str          # added, removed, modified, reexported, rewritten, unchanged, untracked
    detail: str = ""


def same_shape_state(path: str) -> tuple[str, str]:
    """Name the case where the bytes moved and the geometry did not.

    A mesh that was written again is a re-export. A part file whose feature
    tree was edited into the same solid is a rewrite, and the two deserve
    different words because only one of them contains work.
    """
    if model_mod.classify(path) == "parametric":
        return "rewritten", "feature tree edited, resulting solid identical"
    return "reexported", "bytes differ, geometry identical"


class StatusMixin:
    """Comparing the working tree, the index, and HEAD."""

    def geometry_matches(
        self, path: str, data_a: bytes, data_b: bytes, gid_a: str, gid_b: str
    ) -> bool:
        """Do these two files describe the same solid?

        The exact fingerprint is tried first because it is nearly free. The
        tolerance comparison runs only when the fingerprints disagree, which
        is what catches an exporter that writes float noise.
        """
        if gid_a and gid_a == gid_b:
            return True
        if not (gid_a and gid_b) or model_mod.classify(path) != "mesh":
            return False
        from ..geometry import equivalent

        mesh_a = self.load_model(path, data_a).mesh
        mesh_b = self.load_model(path, data_b).mesh
        if mesh_a is None or mesh_b is None:
            return False
        return equivalent(mesh_a, mesh_b)[0]

    def status(self) -> tuple[list[StatusEntry], list[StatusEntry]]:
        """Return what is staged, and what changed in the working tree."""
        from ..objects import Tree

        head = self.head_commit()
        head_tree = self.tree_obj(self.commit_obj(head).tree) if head else Tree()
        index = self.read_index()

        staged: list[StatusEntry] = []
        for path in sorted(set(index) | set(head_tree.entries)):
            before = head_tree.entries.get(path)
            after = index.get(path)
            if before is None and after is not None:
                staged.append(StatusEntry(path, "added"))
            elif after is None and before is not None:
                staged.append(StatusEntry(path, "removed"))
            elif before and after and before.oid != after.oid:
                if self.geometry_matches(
                    path,
                    self.store.get_typed(before.oid, "blob"),
                    self.store.get_typed(after.oid, "blob"),
                    before.gid,
                    after.gid,
                ):
                    staged.append(StatusEntry(path, *same_shape_state(path)))
                else:
                    staged.append(StatusEntry(path, "modified"))

        working: list[StatusEntry] = []
        for path in sorted(set(self.walk_worktree()) | set(index)):
            full = os.path.join(self.root, path)
            tracked = index.get(path)
            if not os.path.exists(full):
                if tracked:
                    working.append(StatusEntry(path, "removed"))
                continue
            if tracked is None:
                working.append(StatusEntry(path, "untracked"))
                continue
            with open(full, "rb") as handle:
                data = handle.read()
            if hash_object("blob", data) == tracked.oid:
                continue
            gid = self.describe(path, data)["gid"]
            if self.geometry_matches(
                path, self.store.get_typed(tracked.oid, "blob"), data, tracked.gid, gid
            ):
                working.append(StatusEntry(path, *same_shape_state(path)))
            else:
                working.append(StatusEntry(path, "modified"))
        self.flush_cache()
        return staged, working
