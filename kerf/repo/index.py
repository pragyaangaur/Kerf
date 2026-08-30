"""The staging area, and the cache that keeps it fast.

Reading geometry out of a file is the expensive part of every command, so the
result is memoised against the hash of the file bytes. Staging the same part
twice, or asking for status twice, costs one read.
"""

from __future__ import annotations

import json
import os
from typing import Iterable

from .. import model as model_mod
from ..objects import TreeEntry, hash_object
from .errors import RepoError


class IndexMixin:
    """Staging and the derived geometry cache."""

    def _load_cache(self) -> dict:
        if self._cache is None:
            try:
                with open(self.cache_path) as handle:
                    self._cache = json.load(handle)
            except (OSError, json.JSONDecodeError):
                self._cache = {}
        return self._cache

    def _save_cache(self) -> None:
        if self._cache is None:
            return
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        temp = self.cache_path + ".tmp"
        with open(temp, "w") as handle:
            json.dump(self._cache, handle)
        os.replace(temp, self.cache_path)

    def describe(self, path: str, data: bytes) -> dict:
        """Geometry id and measurements for a blob, cached on its byte hash."""
        oid = hash_object("blob", data)
        cache = self._load_cache()
        if oid in cache:
            return cache[oid]
        model = model_mod.load(path, data, self.config.get("eval_resolution", 56))
        info = {
            "kind": model.kind,
            "gid": model.geometry_id(),
            "stats": model.stats(),
            "error": model.error,
            "size": len(data),
        }
        cache[oid] = info
        self._save_cache()
        return info

    def load_model(self, path: str, data: bytes) -> model_mod.Model:
        return model_mod.load(path, data, self.config.get("eval_resolution", 56))

    def model_at(self, rev: str, path: str) -> model_mod.Model:
        tree = self.commit_tree(rev)
        entry = tree.entries.get(path)
        if entry is None:
            raise RepoError(f"{path} does not exist at {rev}")
        return self.load_model(path, self.store.get_typed(entry.oid, "blob"))

    def read_index(self) -> dict[str, TreeEntry]:
        with open(os.path.join(self.kerf, "index.json")) as handle:
            raw = json.load(handle)
        return {
            path: TreeEntry(
                path=path, oid=entry["oid"], gid=entry["gid"],
                kind=entry["kind"], size=entry.get("size", 0),
            )
            for path, entry in raw.get("entries", {}).items()
        }

    def write_index(self, entries: dict[str, TreeEntry]) -> None:
        raw = {
            "entries": {
                path: {"oid": e.oid, "gid": e.gid, "kind": e.kind, "size": e.size}
                for path, e in entries.items()
            }
        }
        temp = os.path.join(self.kerf, "index.json.tmp")
        with open(temp, "w") as handle:
            json.dump(raw, handle, indent=2)
        os.replace(temp, os.path.join(self.kerf, "index.json"))

    def stage_entry(self, relative: str) -> TreeEntry:
        full = os.path.join(self.root, relative)
        if not os.path.isfile(full):
            raise RepoError(f"no such file: {relative}")
        with open(full, "rb") as handle:
            data = handle.read()
        info = self.describe(relative, data)
        oid = self.store.put("blob", data)
        return TreeEntry(
            path=relative, oid=oid, gid=info["gid"], kind=info["kind"], size=len(data)
        )

    def add(self, paths: Iterable[str], force: bool = False) -> list[TreeEntry]:
        """Stage files for the next revision, honouring locks other people hold."""
        index = self.read_index()
        staged: list[TreeEntry] = []
        for raw in paths:
            for relative in self._expand(raw):
                blocker = self.lock_blocker(relative)
                if blocker and not force:
                    reason = blocker.get("reason", "no reason given")
                    raise RepoError(
                        f"{relative} is locked by {blocker['owner']} ({reason}), "
                        f"so use --force to stage it anyway"
                    )
                entry = self.stage_entry(relative)
                index[relative] = entry
                staged.append(entry)
        self.write_index(index)
        return staged

    def unstage(self, paths: Iterable[str]) -> None:
        index = self.read_index()
        for raw in paths:
            index.pop(self._to_rel(raw), None)
        self.write_index(index)
