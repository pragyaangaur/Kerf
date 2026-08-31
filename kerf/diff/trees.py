"""Comparing two whole revisions."""

from __future__ import annotations

from typing import Optional

from ..model import Model
from .models import ModelDiff, diff_models


def model_from_entry(repo, path: str, entry) -> Optional[Model]:
    """Load the model a tree entry points at."""
    if entry is None:
        return None
    return repo.load_model(path, repo.store.get_typed(entry.oid, "blob"))


def diff_trees(
    repo,
    tree_old,
    tree_new,
    resolution: int = 56,
    volumetric: bool = True,
    paths: Optional[list[str]] = None,
) -> list[ModelDiff]:
    """Compare two trees. A file that moved keeps its history, because a
    rename is found by matching geometry ids rather than by matching names."""
    old_entries = dict(tree_old.entries)
    new_entries = dict(tree_new.entries)

    # Both are walked in sorted order. Two files can be deleted with the same
    # geometry, and which one a new file is reported as a rename of has to be
    # the same answer on every run.
    dropped = set(old_entries) - set(new_entries)
    appeared = set(new_entries) - set(old_entries)
    renames: dict[str, str] = {}
    by_geometry: dict[str, list[str]] = {}
    for path in sorted(dropped):
        gid = old_entries[path].gid
        if gid:
            by_geometry.setdefault(gid, []).append(path)
    for path in sorted(appeared):
        gid = new_entries[path].gid
        candidates = by_geometry.get(gid) if gid else None
        if candidates:
            renames[path] = candidates.pop(0)

    results: list[ModelDiff] = []
    all_paths = sorted(set(old_entries) | set(new_entries))
    if paths:
        wanted = set(paths)
        all_paths = [p for p in all_paths if p in wanted or renames.get(p) in wanted]

    for path in all_paths:
        if path in renames.values() and path not in new_entries:
            continue                                 # reported under its new name
        old_entry = old_entries.get(path) or old_entries.get(renames.get(path, ""))
        new_entry = new_entries.get(path)
        result = diff_models(
            path,
            model_from_entry(repo, path, old_entry),
            model_from_entry(repo, path, new_entry),
            resolution,
            volumetric,
        )
        if path in renames:
            already_same = result.status in ("unchanged", "reexported")
            result.status = "renamed" if already_same else "renamed+modified"
            result.old_path = renames[path]
        if (
            result.status == "unchanged"
            and old_entry
            and new_entry
            and old_entry.oid == new_entry.oid
        ):
            continue
        results.append(result)
    return results
