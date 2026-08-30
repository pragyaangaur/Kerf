"""Merging two whole revisions.

Meshes cannot be merged. There is no meaningful union of two edits to a
triangle soup, so kerf takes the side that changed when only one side did,
and raises a conflict when both did. The advice that comes with the conflict
is to lock the file next time, because that is the workflow that actually
works for a binary part.
"""

from __future__ import annotations

from typing import Optional

from ..model import classify
from ..parametric import Part
from .conflicts import Conflict, FileMerge, MergeResult
from .parts import merge_parts


def blob(repo, entry) -> Optional[bytes]:
    return None if entry is None else repo.store.get_typed(entry.oid, "blob")


def merge_trees(
    repo,
    base_tree,
    our_tree,
    their_tree,
    check_interference: bool = True,
    check_equations: bool = True,
) -> MergeResult:
    """Merge every file in two revisions against their common ancestor."""
    result = MergeResult()
    paths = sorted(
        set(base_tree.entries) | set(our_tree.entries) | set(their_tree.entries)
    )

    for path in paths:
        original = base_tree.entries.get(path)
        ours = our_tree.entries.get(path)
        theirs = their_tree.entries.get(path)

        if ours is None and theirs is None:
            continue
        if ours is not None and theirs is not None and ours.oid == theirs.oid:
            result.files.append(FileMerge(path, "unchanged", blob(repo, ours)))
            continue
        if ours is None:
            if original is None:
                result.files.append(
                    FileMerge(path, "added", blob(repo, theirs),
                              notes=["added on the incoming branch"])
                )
            else:
                result.files.append(
                    FileMerge(path, "conflict", None, [
                        Conflict(path, "file", path,
                                 detail="deleted here and modified on the incoming branch")
                    ])
                )
            continue
        if theirs is None:
            if original is None:
                result.files.append(FileMerge(path, "ours", blob(repo, ours)))
            elif original.oid == ours.oid:
                result.files.append(
                    FileMerge(path, "removed", None, notes=["deleted on the incoming branch"])
                )
            else:
                result.files.append(
                    FileMerge(path, "conflict", None, [
                        Conflict(path, "file", path,
                                 detail="modified here and deleted on the incoming branch")
                    ])
                )
            continue

        if original is not None and original.oid == ours.oid:
            result.files.append(
                FileMerge(path, "theirs", blob(repo, theirs),
                          notes=["taken from the incoming branch"])
            )
            continue
        if original is not None and original.oid == theirs.oid:
            result.files.append(FileMerge(path, "ours", blob(repo, ours)))
            continue
        if ours.gid and ours.gid == theirs.gid:
            result.files.append(
                FileMerge(path, "ours", blob(repo, ours),
                          notes=["both sides re-exported identical geometry"])
            )
            continue

        if classify(path) == "parametric":
            try:
                base_part = Part.loads(blob(repo, original)) if original else None
                our_part = Part.loads(blob(repo, ours))
                their_part = Part.loads(blob(repo, theirs))
            except Exception as error:               # noqa: BLE001
                result.files.append(
                    FileMerge(path, "conflict", None, [
                        Conflict(path, "file", path, detail=f"cannot parse part: {error}")
                    ])
                )
                continue
            merged, conflicts, notes = merge_parts(
                path, base_part, our_part, their_part,
                check_interference, check_equations,
            )
            if conflicts:
                result.files.append(
                    FileMerge(path, "conflict", None, conflicts, notes,
                              blob(repo, ours), blob(repo, theirs))
                )
            else:
                result.files.append(FileMerge(path, "merged", merged.dumps(), notes=notes))
            continue

        result.files.append(
            FileMerge(
                path, "conflict", None,
                [Conflict(path, "file", path,
                          detail="both sides changed a binary CAD file, so pick a side "
                                 "and lock the file next time")],
                ours_data=blob(repo, ours), theirs_data=blob(repo, theirs),
            )
        )

    for merged_file in result.files:
        result.conflicts.extend(merged_file.conflicts)
    return result
