"""Branches, HEAD, and turning what a user typed into a commit id."""

from __future__ import annotations

import os
from typing import Optional

from ..objects import Commit, Tree
from .errors import RepoError


class RefMixin:
    """Reference handling for the repository."""

    def _ref_path(self, ref: str) -> str:
        return os.path.join(self.kerf, ref)

    def head_ref(self) -> Optional[str]:
        """The branch HEAD points at, or None when HEAD is detached."""
        with open(os.path.join(self.kerf, "HEAD")) as handle:
            content = handle.read().strip()
        return content[5:].strip() if content.startswith("ref: ") else None

    def head_commit(self) -> Optional[str]:
        ref = self.head_ref()
        if ref is None:
            with open(os.path.join(self.kerf, "HEAD")) as handle:
                return handle.read().strip() or None
        return self.read_ref(ref)

    def current_branch(self) -> Optional[str]:
        ref = self.head_ref()
        return ref.rsplit("/", 1)[-1] if ref else None

    def read_ref(self, ref: str) -> Optional[str]:
        path = self._ref_path(ref)
        if not os.path.exists(path):
            return None
        with open(path) as handle:
            return handle.read().strip() or None

    def write_ref(self, ref: str, oid: str) -> None:
        path = self._ref_path(ref)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(oid + "\n")

    def set_head_to_branch(self, name: str) -> None:
        with open(os.path.join(self.kerf, "HEAD"), "w") as handle:
            handle.write(f"ref: refs/heads/{name}\n")

    def set_head_detached(self, oid: str) -> None:
        with open(os.path.join(self.kerf, "HEAD"), "w") as handle:
            handle.write(oid + "\n")

    def branches(self) -> dict[str, str]:
        base = os.path.join(self.kerf, "refs", "heads")
        found = {}
        for dirpath, _, files in os.walk(base):
            for name in files:
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, base).replace(os.sep, "/")
                with open(full) as handle:
                    found[relative] = handle.read().strip()
        return found

    def create_branch(self, name: str, oid: str | None = None) -> str:
        if name in self.branches():
            raise RepoError(f"branch {name!r} already exists")
        target = oid or self.head_commit()
        if target is None:
            raise RepoError("cannot branch before the first commit")
        self.write_ref(f"refs/heads/{name}", target)
        return target

    def delete_branch(self, name: str) -> None:
        if name == self.current_branch():
            raise RepoError(f"cannot delete the checked out branch {name!r}")
        path = self._ref_path(f"refs/heads/{name}")
        if not os.path.exists(path):
            raise RepoError(f"no such branch: {name}")
        os.remove(path)

    def resolve(self, rev: str) -> str:
        """Turn HEAD, HEAD~2, a branch name, or a short id into a commit id."""
        rev = rev.strip()
        base, _, back = rev.partition("~")
        steps = int(back) if back else 0
        oid: Optional[str]
        if base in ("HEAD", "@", ""):
            oid = self.head_commit()
        elif base in self.branches():
            oid = self.branches()[base]
        elif os.path.exists(self._ref_path(f"refs/tags/{base}")):
            oid = self.read_ref(f"refs/tags/{base}")
        else:
            oid = self.store.resolve_prefix(base) if len(base) >= 4 else None
        if oid is None:
            raise RepoError(f"cannot resolve revision {rev!r}")
        for _ in range(steps):
            commit = self.commit_obj(oid)
            if not commit.parents:
                raise RepoError(f"{rev}: reached the root commit")
            oid = commit.parents[0]
        return oid

    def commit_obj(self, oid: str) -> Commit:
        return Commit.deserialize(self.store.get_typed(oid, "commit"))

    def tree_obj(self, oid: str) -> Tree:
        return Tree.deserialize(self.store.get_typed(oid, "tree"))

    def commit_tree(self, rev_or_oid: str) -> Tree:
        oid = rev_or_oid if _is_oid(rev_or_oid) else self.resolve(rev_or_oid)
        return self.tree_obj(self.commit_obj(oid).tree)


def _is_oid(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)
