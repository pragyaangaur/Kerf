"""Claiming a part nobody can merge for you.

Some formats cannot be merged by any tool. Kerf says so instead of pretending
otherwise, and offers the workflow that does work for a binary part, which is
to claim it before editing it.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from .errors import RepoError


class LockMixin:
    """Advisory locks, stored in the repository."""

    def locks(self) -> dict[str, dict]:
        with open(os.path.join(self.kerf, "locks.json")) as handle:
            return json.load(handle).get("locks", {})

    def _write_locks(self, locks: dict[str, dict]) -> None:
        temp = os.path.join(self.kerf, "locks.json.tmp")
        with open(temp, "w") as handle:
            json.dump({"locks": locks}, handle, indent=2)
        os.replace(temp, os.path.join(self.kerf, "locks.json"))

    def lock(self, path: str, reason: str = "", owner: str | None = None) -> dict:
        owner = owner or self.author
        locks = self.locks()
        existing = locks.get(path)
        if existing and existing["owner"] != owner:
            raise RepoError(f"{path} is already locked by {existing['owner']}")
        entry = {"owner": owner, "reason": reason, "since": int(time.time())}
        locks[path] = entry
        self._write_locks(locks)
        return entry

    def unlock(self, path: str, owner: str | None = None, force: bool = False) -> None:
        owner = owner or self.author
        locks = self.locks()
        existing = locks.get(path)
        if existing is None:
            raise RepoError(f"{path} is not locked")
        if existing["owner"] != owner and not force:
            raise RepoError(f"{path} is locked by {existing['owner']}, so use --force")
        del locks[path]
        self._write_locks(locks)

    def lock_blocker(self, path: str) -> Optional[dict]:
        """The lock that stops this author from changing the file, if there is one."""
        entry = self.locks().get(path)
        if entry and entry["owner"] != self.author:
            return entry
        return None
