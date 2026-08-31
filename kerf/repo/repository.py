"""The repository itself.

Everything on disk lives under .kerf, and the layout follows git closely
enough that the ideas transfer. The parts that differ are the geometry id on
every tree entry, the geometry cache, and the lock file.
"""

from __future__ import annotations

import fnmatch
import getpass
import json
import os
import time
from typing import Iterable, Optional

from ..objects import Commit, ObjectStore, Tree
from .errors import RepoError
from .index import IndexMixin
from .locks import LockMixin
from .refs import RefMixin
from .status import StatusMixin

KERF_DIR = ".kerf"
DEFAULT_BRANCH = "main"

DEFAULT_IGNORES = [
    ".kerf/*", ".git/*", "*.pyc", "__pycache__/*", ".DS_Store",
    "*.tmp", "*.bak", "~$*", "*.swp",
]


def find_repo(start: str = ".") -> str:
    """Walk up from a directory until a repository turns up."""
    current = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(current, KERF_DIR)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise RepoError("not a kerf repository (run `kerf init`)")
        current = parent


class Repo(RefMixin, IndexMixin, StatusMixin, LockMixin):
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.kerf = os.path.join(self.root, KERF_DIR)
        if not os.path.isdir(self.kerf):
            raise RepoError(f"no kerf repository at {self.root}")
        self.store = ObjectStore(os.path.join(self.kerf, "objects"))
        self.cache_path = os.path.join(self.kerf, "cache", "geometry.json")
        self._cache: Optional[dict] = None
        self._generation: dict[str, int] = {}
        self._config: Optional[dict] = None
        self._ignores: Optional[list[str]] = None
        self._cache_dirty = False
        self._models: dict[tuple[str, str], object] = {}

    @staticmethod
    def init(root: str, author: str | None = None) -> "Repo":
        kerf = os.path.join(os.path.abspath(root), KERF_DIR)
        if os.path.isdir(kerf):
            raise RepoError(f"repository already exists at {root}")
        for sub in ("objects", "refs/heads", "refs/tags", "cache"):
            os.makedirs(os.path.join(kerf, sub), exist_ok=True)
        with open(os.path.join(kerf, "HEAD"), "w") as handle:
            handle.write(f"ref: refs/heads/{DEFAULT_BRANCH}\n")
        config = {
            "author": author or getpass.getuser(),
            "created": int(time.time()),
            "eval_resolution": 56,
            "diff_resolution": 56,
        }
        with open(os.path.join(kerf, "config.json"), "w") as handle:
            json.dump(config, handle, indent=2)
        with open(os.path.join(kerf, "index.json"), "w") as handle:
            json.dump({"entries": {}}, handle)
        with open(os.path.join(kerf, "locks.json"), "w") as handle:
            json.dump({"locks": {}}, handle)
        ignore = os.path.join(os.path.abspath(root), ".kerfignore")
        if not os.path.exists(ignore):
            with open(ignore, "w") as handle:
                handle.write("# Files kerf should not track\n*.log\nexports/\n")
        return Repo(root)

    @property
    def config(self) -> dict:
        """The repository settings, read once per Repo object.

        Every file staged, and every file status looks at, asks for the
        evaluation resolution. Reading the file each time turned one setting
        into one open() per part.
        """
        if self._config is None:
            with open(os.path.join(self.kerf, "config.json")) as handle:
                self._config = json.load(handle)
        return self._config

    def set_config(self, key: str, value) -> None:
        config = dict(self.config)
        config[key] = value
        with open(os.path.join(self.kerf, "config.json"), "w") as handle:
            json.dump(config, handle, indent=2)
        self._config = config

    @property
    def author(self) -> str:
        return str(self.config.get("author", "unknown"))

    def history(self, start: str | None = None, limit: int | None = None) -> list[tuple[str, Commit]]:
        """Commits reachable from a starting point, newest first.

        Timestamps only have one second of resolution, and a quick sequence of
        commits can share one. Generation number breaks the tie, so a child is
        never listed below its own parent.
        """
        head = start or self.head_commit()
        if head is None:
            return []
        seen: set[str] = set()
        frontier = [head]
        found: list[tuple[str, Commit]] = []
        while frontier:
            oid = frontier.pop()
            if oid in seen:
                continue
            seen.add(oid)
            commit = self.commit_obj(oid)
            found.append((oid, commit))
            frontier.extend(commit.parents)

        generation = {oid: self.generation(oid) for oid, _ in found}
        found.sort(key=lambda pair: (-pair[1].timestamp, -generation[pair[0]], pair[0]))
        return found[:limit] if limit else found

    def ancestors(self, oid: str) -> set[str]:
        seen: set[str] = set()
        stack = [oid]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self.commit_obj(current).parents)
        return seen

    def generation(self, oid: str) -> int:
        """How many commits deep this one sits, counting from the root.

        This is the ordering a merge base needs. A parent always has a
        smaller generation than its child, which is a fact about the graph
        rather than about the clock on whichever machine wrote the commit.
        """
        depth = self._generation
        stack = [oid]
        while stack:
            current = stack[-1]
            if current in depth:
                stack.pop()
                continue
            parents = self.commit_obj(current).parents
            missing = [p for p in parents if p not in depth]
            if missing:
                stack.extend(missing)
                continue
            depth[current] = 1 + max((depth[p] for p in parents), default=0)
            stack.pop()
        return depth[oid]

    def merge_base(self, a: str, b: str) -> Optional[str]:
        """The most recent commit both revisions descend from.

        Ranking the shared ancestors by timestamp looks right and is not.
        Timestamps have one second of resolution, so a quick run of commits
        shares one, and the answer then came down to which order a set
        happened to iterate in. Picking the wrong base makes the three way
        merge see changes on a side that never made them.

        Generation is the ordering the graph itself provides. Ties are broken
        by timestamp and then by object id, so the answer is the same on
        every machine and on every run.
        """
        shared = self.ancestors(a) & self.ancestors(b)
        if not shared:
            return None
        return max(
            sorted(shared),
            key=lambda oid: (self.generation(oid), self.commit_obj(oid).timestamp),
        )

    def ignores(self) -> list[str]:
        """The ignore patterns, read once per Repo object.

        is_ignored is asked about every file in the working tree, so reading
        .kerfignore inside it meant re-reading the file thousands of times
        for one status.
        """
        if self._ignores is None:
            patterns = list(DEFAULT_IGNORES)
            path = os.path.join(self.root, ".kerfignore")
            if os.path.exists(path):
                with open(path) as handle:
                    for line in handle:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            patterns.append(line)
            self._ignores = patterns
        return self._ignores

    def is_ignored(self, relative: str) -> bool:
        for pattern in self.ignores():
            if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(
                relative, pattern.rstrip("/") + "/*"
            ):
                return True
            if pattern.endswith("/") and relative.startswith(pattern):
                return True
        return False

    def walk_worktree(self) -> list[str]:
        found = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in (KERF_DIR, ".git", "__pycache__")]
            for name in filenames:
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, self.root).replace(os.sep, "/")
                if not self.is_ignored(relative):
                    found.append(relative)
        return sorted(found)

    def _to_rel(self, raw: str) -> str:
        """Read a path the user typed and return it relative to the root.

        A relative path is read against the working directory first, which is
        what somebody standing in a subdirectory expects. That reading is only
        used when it lands inside the repository, because the same name can
        exist in an unrelated directory the caller happens to be standing in.
        """
        if os.path.isabs(raw):
            return os.path.relpath(raw, self.root).replace(os.sep, "/")
        from_cwd = os.path.abspath(raw)
        if os.path.exists(from_cwd) and self._inside(from_cwd):
            return os.path.relpath(from_cwd, self.root).replace(os.sep, "/")
        return os.path.normpath(raw).replace(os.sep, "/")

    def _inside(self, path: str) -> bool:
        """Is an absolute path within this repository?"""
        root = os.path.join(os.path.realpath(self.root), "")
        return os.path.realpath(path).startswith(root)

    def _expand(self, raw: str) -> list[str]:
        relative = self._to_rel(raw)
        full = os.path.join(self.root, relative)
        if os.path.isdir(full):
            found = []
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = [d for d in dirnames if d not in (KERF_DIR, ".git", "__pycache__")]
                for name in filenames:
                    inner = os.path.relpath(
                        os.path.join(dirpath, name), self.root
                    ).replace(os.sep, "/")
                    if not self.is_ignored(inner):
                        found.append(inner)
            return sorted(found)
        if relative == "." or raw in (".", "*"):
            return self.walk_worktree()
        if not os.path.exists(full):
            raise RepoError(f"no such file: {raw}")
        return [relative]

    def commit(
        self,
        message: str,
        author: str | None = None,
        parents: list[str] | None = None,
        meta: dict | None = None,
        allow_empty: bool = False,
    ) -> str:
        index = self.read_index()
        head = self.head_commit()
        if parents is None:
            parents = [head] if head else []
        tree = Tree(entries=dict(index))
        tree_oid = self.store.put("tree", tree.serialize())
        if not allow_empty and head is not None and len(parents) == 1:
            if self.commit_obj(head).tree == tree_oid:
                raise RepoError("nothing to commit (the index matches HEAD)")
        commit = Commit(
            tree=tree_oid,
            parents=parents,
            author=author or self.author,
            timestamp=int(time.time()),
            message=message,
            meta=meta or {},
        )
        oid = self.store.put("commit", commit.serialize())
        ref = self.head_ref()
        if ref:
            self.write_ref(ref, oid)
        else:
            self.set_head_detached(oid)
        return oid

    def checkout(self, rev: str, force: bool = False) -> str:
        """Replace the working tree with one revision.

        Any tracked change counts as work to protect, including a re-export.
        Throwing away bytes without asking is worse than one extra prompt.
        """
        _, working = self.status()
        dirty = [entry for entry in working if entry.state != "untracked"]
        if dirty and not force:
            names = ", ".join(entry.path for entry in dirty[:4])
            raise RepoError(f"uncommitted changes would be lost: {names} (use --force)")

        oid = self.resolve(rev)
        new_tree = self.tree_obj(self.commit_obj(oid).tree)
        old_index = self.read_index()

        for path in old_index:
            if path not in new_tree.entries:
                full = os.path.join(self.root, path)
                if os.path.exists(full):
                    os.remove(full)
                    self._prune_dirs(os.path.dirname(full))

        for path, entry in new_tree.entries.items():
            full = os.path.join(self.root, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as handle:
                handle.write(self.store.get_typed(entry.oid, "blob"))

        self.write_index(dict(new_tree.entries))
        if rev in self.branches():
            self.set_head_to_branch(rev)
        else:
            self.set_head_detached(oid)
        return oid

    def _prune_dirs(self, path: str) -> None:
        while os.path.isdir(path) and path != self.root and not os.listdir(path):
            os.rmdir(path)
            path = os.path.dirname(path)

    def restore(self, rev: str, paths: Iterable[str]) -> list[str]:
        tree = self.commit_tree(rev)
        index = self.read_index()
        done = []
        for raw in paths:
            relative = self._to_rel(raw)
            entry = tree.entries.get(relative)
            if entry is None:
                raise RepoError(f"{relative} does not exist at {rev}")
            full = os.path.join(self.root, relative)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as handle:
                handle.write(self.store.get_typed(entry.oid, "blob"))
            index[relative] = entry
            done.append(relative)
        self.write_index(index)
        return done

    def worktree_tree(self) -> Tree:
        """The tracked files as they are on disk right now.

        Blobs are written to the store so the comparison can read them the
        same way it reads any other revision. Objects are addressed by their
        content, so a file that is later staged costs nothing more.
        """
        tree = Tree()
        index = self.read_index()
        for path in sorted(index):
            if os.path.exists(os.path.join(self.root, path)):
                tree.entries[path] = self.stage_entry(path)
        self.flush_cache()
        return tree

    def export(self, rev: str, dest: str) -> int:
        """Write every file of one revision into a plain directory."""
        tree = self.commit_tree(rev)
        os.makedirs(dest, exist_ok=True)
        for path, entry in tree.entries.items():
            out = os.path.join(dest, path)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as handle:
                handle.write(self.store.get_typed(entry.oid, "blob"))
        return len(tree.entries)

    def stats(self) -> dict:
        tracked = self.read_index()
        working = sum(
            os.path.getsize(os.path.join(self.root, path))
            for path in tracked
            if os.path.exists(os.path.join(self.root, path))
        )
        return {
            "commits": len(self.history()),
            "branches": len(self.branches()),
            "tracked_files": len(tracked),
            "objects": sum(1 for _ in self.store.iter_oids()),
            "store_bytes": self.store.total_bytes(),
            "worktree_bytes": working,
            "locks": len(self.locks()),
        }
