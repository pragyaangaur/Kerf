"""Three way merge of two feature trees.

Every feature carries a stable id, so the merge can work per feature and per
parameter instead of per line. Two people who touch different features get a
clean merge. Two people who touch the same field get a conflict that names
the field.
"""

from __future__ import annotations

import copy
from typing import Optional

from ..parametric import Feature, Part
from .conflicts import Conflict, short
from .equations import detect_equation_breaks
from .interference import detect_interference


def merge_parts(
    path: str,
    base: Optional[Part],
    ours: Part,
    theirs: Part,
    check_interference: bool = True,
    check_equations: bool = True,
) -> tuple[Part, list[Conflict], list[str]]:
    """Merge theirs into ours, using base as the common ancestor."""
    base = base or Part()
    merged = ours.copy()
    conflicts: list[Conflict] = []
    notes: list[str] = []

    for attribute in ("name", "units"):
        original = getattr(base, attribute, None)
        our_value = getattr(ours, attribute)
        their_value = getattr(theirs, attribute)
        if our_value == their_value:
            continue
        if our_value == original:
            setattr(merged, attribute, their_value)
        elif their_value != original:
            conflicts.append(Conflict(path, "field", attribute, original, our_value, their_value))

    for key in sorted(set(base.parameters) | set(ours.parameters) | set(theirs.parameters)):
        original = base.parameters.get(key)
        our_value = ours.parameters.get(key)
        their_value = theirs.parameters.get(key)
        if our_value == their_value:
            continue
        if our_value == original:
            if their_value is None:
                merged.parameters.pop(key, None)
                notes.append(f"parameter {key} removed by theirs")
            else:
                merged.parameters[key] = their_value
                notes.append(f"parameter {key} -> {their_value} from theirs")
        elif their_value == original:
            continue
        else:
            conflicts.append(
                Conflict(path, "parameter", key, original, our_value, their_value)
            )

    base_features = {item.id: item for item in base.features}
    our_features = {item.id: item for item in ours.features}
    their_features = {item.id: item for item in theirs.features}

    theirs_added: list[str] = []
    for feature_id, their_feature in their_features.items():
        original = base_features.get(feature_id)
        our_feature = our_features.get(feature_id)
        if our_feature is None and original is None:
            merged.features.append(copy.deepcopy(their_feature))
            theirs_added.append(feature_id)
            notes.append(f"feature {their_feature.label()} added from theirs")
            continue
        if our_feature is None and original is not None:
            if their_feature.fields() != original.fields():
                conflicts.append(
                    Conflict(
                        path, "feature", feature_id, "present", "deleted", "modified",
                        detail="deleted on our side and modified on theirs",
                    )
                )
            continue
        merged_feature, feature_conflicts, feature_notes = merge_feature(
            path, original, our_feature, their_feature
        )
        conflicts.extend(feature_conflicts)
        notes.extend(feature_notes)
        position = next(i for i, item in enumerate(merged.features) if item.id == feature_id)
        merged.features[position] = merged_feature

    for feature_id, original in base_features.items():
        if feature_id in their_features:
            continue
        our_feature = our_features.get(feature_id)
        if our_feature is None:
            continue
        if our_feature.fields() != original.fields():
            conflicts.append(
                Conflict(
                    path, "feature", feature_id, "present", "modified", "deleted",
                    detail="modified on our side and deleted on theirs",
                )
            )
        else:
            merged.features = [item for item in merged.features if item.id != feature_id]
            notes.append(f"feature {original.label()} removed by theirs")

    common = [
        item.id for item in base.features
        if item.id in our_features and item.id in their_features
    ]
    our_order = [fid for fid in (item.id for item in ours.features) if fid in common]
    their_order = [fid for fid in (item.id for item in theirs.features) if fid in common]
    base_order = [fid for fid in (item.id for item in base.features) if fid in common]
    if our_order != their_order:
        if our_order == base_order:
            # Their order decides where every feature they have goes, which
            # includes the ones they added. Anything only we have is not in
            # that order at all, so it keeps the place it holds now, just
            # after whatever it currently follows. The key is worked out
            # before the sort, because list.sort empties the list while it
            # is running the key function over it.
            wanted = {item.id: i for i, item in enumerate(theirs.features)}
            rank: dict[str, tuple[int, int]] = {}
            anchor = -1
            for offset, item in enumerate(merged.features):
                if item.id in wanted:
                    anchor = wanted[item.id]
                    rank[item.id] = (anchor, 0)
                else:
                    rank[item.id] = (anchor, offset + 1)
            merged.features.sort(key=lambda item: rank[item.id])
            notes.append("feature order taken from theirs")
        elif their_order != base_order:
            conflicts.append(
                Conflict(
                    path, "order", "feature order", base_order, our_order, their_order,
                    detail="both sides reordered the feature tree",
                )
            )

    # The validity gates run only on a merge that is otherwise clean. There is
    # no point telling somebody the merged part will not rebuild when they
    # still have to resolve a conflict that changes it.
    if not conflicts and check_equations:
        conflicts.extend(detect_equation_breaks(path, merged, base, ours, theirs))

    if not conflicts and check_interference:
        ours_added = [item.id for item in ours.features if item.id not in base_features]
        conflicts.extend(detect_interference(path, merged, ours_added, theirs_added))

    return merged, conflicts, notes


def merge_feature(
    path: str, base: Optional[Feature], ours: Feature, theirs: Feature
) -> tuple[Feature, list[Conflict], list[str]]:
    """Merge one feature, field by field."""
    conflicts: list[Conflict] = []
    notes: list[str] = []
    merged = Feature(
        id=ours.id, type=ours.type, op=ours.op, name=ours.name,
        params=dict(ours.params), suppressed=ours.suppressed,
    )
    original = base or Feature(id=ours.id, type=ours.type)

    for attribute in ("type", "op", "name", "suppressed"):
        was = getattr(original, attribute)
        our_value = getattr(ours, attribute)
        their_value = getattr(theirs, attribute)
        if our_value == their_value:
            continue
        if our_value == was:
            setattr(merged, attribute, their_value)
            notes.append(f"{ours.label()}.{attribute} -> {their_value} from theirs")
        elif their_value != was:
            conflicts.append(
                Conflict(path, "field", f"{ours.label()}.{attribute}", was, our_value, their_value)
            )

    for key in sorted(set(original.params) | set(ours.params) | set(theirs.params)):
        was = original.params.get(key)
        our_value = ours.params.get(key)
        their_value = theirs.params.get(key)
        if our_value == their_value:
            continue
        if our_value == was:
            if their_value is None:
                merged.params.pop(key, None)
            else:
                merged.params[key] = their_value
            notes.append(f"{ours.label()}.{key} -> {short(their_value)} from theirs")
        elif their_value == was:
            continue
        else:
            combined = merge_vector(was, our_value, their_value)
            if combined is not None:
                merged.params[key] = combined
                notes.append(f"{ours.label()}.{key} merged one axis at a time")
                continue
            conflicts.append(
                Conflict(path, "field", f"{ours.label()}.{key}", was, our_value, their_value)
            )
    return merged, conflicts, notes


def merge_vector(base, ours, theirs):
    """Merge a list where the two sides moved different components.

    Moving a feature along x while somebody else moves it along y is two edits
    that can both survive. Returns None when the same component changed on
    both sides.
    """
    if not (isinstance(ours, list) and isinstance(theirs, list) and isinstance(base, list)):
        return None
    if not len(ours) == len(theirs) == len(base):
        return None
    combined = []
    for index in range(len(base)):
        if ours[index] == theirs[index]:
            combined.append(ours[index])
        elif ours[index] == base[index]:
            combined.append(theirs[index])
        elif theirs[index] == base[index]:
            combined.append(ours[index])
        else:
            return None
    return combined
